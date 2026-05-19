"""Workflow orchestrator: Python-driven plan→execute→verify loop with reflection guardrails.

Architecture (specs3.md compliant):
  The Python loop drives execution entirely. The model acts as a JSON oracle called
  via litellm directly with response_format={"type":"json_object"} — the only JSON
  mode Ollama actually supports. No response_schema / structured_output dependency.

  Reflection guardrail (specs3 #2 applied to planning):
    Each oracle call is wrapped in _oracle() which retries up to MAX_REFLECT_RETRIES
    times on JSON parse / schema validation failure, injecting the specific error each
    time so the model can self-correct.

  Cycle:
    1. PLAN   — oracle produces PlanOutput JSON (with reflection on failure)
    2. EXECUTE — LLMAgentBlock workers with composite tools (specs3 #1–#3, #5–#6)
                 + escalation to ALTERNATIVE_MODEL on failure (specs3 #4)
    3. VERIFY  — oracle produces VerifyOutput JSON (with reflection on failure)
    4. LOOP   — repeat until done=True or heartbeat budget exhausted.
"""

import asyncio
import json
import re
import time
from pathlib import Path

import litellm
from pydantic import BaseModel, ValidationError
from rich.live import Live

from agenticblocks.blocks.llm.agent import AgentInput, LLMAgentBlock

from .config import (
    get_agent_debug,
    get_agent_heartbeats_scale_factor,
    get_agent_llm_kwargs,
    get_agent_max_heartbeats,
    get_agent_model,
    DEFAULT_MODEL,
)
from .code_index import CODE_INDEX
from .tools import AGENT_PROGRESS, get_project_path
from .workflow_tools import get_workflow_tools
from .orchestrator import (
    BaseOrchestratorStrategy,
    register_orchestrator,
    _build_progress_panel,
    _deduplicate_response,
)
from . import terminal as T
from .i18n import _
from .planner import generate_panorama, refine_plan


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Task(BaseModel):
    id: str
    goal: str           # human-readable objective, e.g. "Create style.css to style index.html"
    commands: list[str] # ordered atomic steps, each executed as a separate worker prompt
    related_files: list[str]  # files the worker must read before acting
    context: str        # operational detail: classes, IDs, APIs, contracts between files
    depends_on: list[str] = []  # ids of tasks that must complete before this one


def _validate_task(task: Task) -> str | None:
    """Return a feedback string if the task is semantically incomplete, else None."""
    errors: list[str] = []
    if not task.goal.strip():
        errors.append(f"task '{task.id}': 'goal' is empty — describe what this task achieves and why.")
    if not task.commands:
        errors.append(f"task '{task.id}': 'commands' is empty — list at least one atomic step.")
    if not task.context.strip():
        errors.append(
            f"task '{task.id}': 'context' is empty — provide operational details "
            "(class names, function signatures, IDs, contracts with other files)."
        )
    # CSS/JS tasks that reference HTML should list the HTML in related_files
    goal_lower = task.goal.lower()
    cmd_text = " ".join(task.commands).lower()
    if any(ext in goal_lower + cmd_text for ext in (".css", ".js", ".ts")) and not task.related_files:
        errors.append(
            f"task '{task.id}': 'related_files' is empty for a CSS/JS task — "
            "list the HTML or source files that define the classes/IDs being targeted."
        )
    return "\n".join(errors) if errors else None


class PlanOutput(BaseModel):
    tasks: list[Task]


class VerifyOutput(BaseModel):
    done: bool
    summary: str              # past-tense if done; what's missing otherwise
    corrections: list[Task]   # empty when done=True


# ---------------------------------------------------------------------------
# Project snapshot (used to prime the oracle without tools)
# ---------------------------------------------------------------------------

def _project_snapshot() -> str:
    """Return a symbol-enriched project snapshot for oracle prompts.

    Uses the code index when available (lists exported symbols per file).
    Falls back to a plain file listing if the index has not been built yet.
    """
    try:
        snap = CODE_INDEX.project_snapshot(max_files=100)
        if not snap.startswith("(index empty"):
            return snap
    except Exception:
        pass

    # Fallback: plain file listing
    SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv",
            ".mypy_cache", "dist", "build", ".env"}
    root = Path(get_project_path())
    if not root.exists():
        return f"(project path not found: {root})"
    files = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file()
        and not any(part in SKIP or part.startswith(".") for part in p.parts)
    )
    return "\n".join(files[:120]) or "(no files found)"


def _read_project_files_for_verify(max_bytes_per_file: int = 3000) -> str:
    """Read actual content of all non-binary project files for the verifier oracle.

    Returns a block with each file's content so the verifier can check the real
    output — not just the worker's self-reported summary.
    """
    SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv",
            ".mypy_cache", "dist", "build", ".env"}
    BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff",
                  ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".gz", ".bin"}
    root = Path(get_project_path())
    if not root.exists():
        return "(project path not found)"

    parts: list[str] = []
    total = 0
    MAX_TOTAL = 12_000

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP or part.startswith(".") for part in p.parts):
            continue
        if p.suffix.lower() in BINARY_EXT:
            continue
        if total >= MAX_TOTAL:
            parts.append("...(remaining files omitted — budget reached)")
            break
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(p.relative_to(root))
        snippet = content[:max_bytes_per_file]
        if len(content) > max_bytes_per_file:
            snippet += f"\n...(truncated, {len(content)} bytes total)"
        block = f"### {rel}\n```\n{snippet}\n```"
        parts.append(block)
        total += len(snippet)

    return "\n\n".join(parts) if parts else "(no readable files in project)"


# ---------------------------------------------------------------------------
# Oracle: single litellm call with JSON mode + reflection
# ---------------------------------------------------------------------------

MAX_REFLECT_RETRIES = 3


async def _oracle(
    schema: type[BaseModel],
    system: str,
    prompt: str,
    *,
    model: str,
    llm_kwargs: dict,
) -> BaseModel | None:
    """Call the LLM with JSON mode, validate against schema, retry on failure.

    Uses response_format={"type":"json_object"} — supported by Ollama.
    On parse or schema error, injects the specific error back (reflection guardrail).
    """
    kwargs = {**llm_kwargs, "response_format": {"type": "json_object"}}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    last_error = ""

    for attempt in range(MAX_REFLECT_RETRIES):
        if attempt > 0:
            fields = {k: str(v.annotation) for k, v in schema.model_fields.items()}
            verify_caution = (
                " IMPORTANT: if this is a VerifyOutput, only set done=true if you have "
                "concrete evidence from the file contents that ALL requirements are met. "
                "When in doubt, set done=false with a specific correction."
            ) if schema.__name__ == "VerifyOutput" else ""
            messages.append({"role": "user", "content": (
                f"[GUARDRAIL — attempt {attempt + 1}/{MAX_REFLECT_RETRIES}]: "
                f"{last_error}. "
                f"Required JSON schema: {json.dumps(fields)}. "
                f"Output ONLY a valid JSON object — no prose, no markdown.{verify_caution}"
            )})

        try:
            resp = await litellm.acompletion(
                model=model, messages=messages, **kwargs
            )
            content = (resp.choices[0].message.content or "").strip()
            T.debug_oracle(schema.__name__, attempt, content)
            # Strip markdown fences if present
            if content.startswith("```"):
                content = re.sub(r"^```[a-z]*\n?", "", content)
                content = re.sub(r"\n?```$", "", content)
            data = json.loads(content)
            result = schema.model_validate(data)
            # Semantic validation for PlanOutput: tasks must be self-contained
            if isinstance(result, PlanOutput):
                feedback = [f for t in result.tasks if (f := _validate_task(t))]
                if feedback:
                    last_error = (
                        "Plan tasks are incomplete:\n" + "\n".join(feedback) +
                        "\nFix ALL flagged tasks before returning the plan."
                    )
                    messages.append({"role": "assistant", "content": content})
                    continue
            return result
        except json.JSONDecodeError as e:
            last_error = f"JSON syntax error: {e}"
            T.debug_oracle_error(schema.__name__, attempt, last_error, content if "content" in dir() else "")
            messages.append({"role": "assistant", "content": content if "content" in dir() else ""})
        except ValidationError as e:
            last_error = f"Schema validation error: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}"
            T.debug_oracle_error(schema.__name__, attempt, last_error, content if "content" in dir() else "")
            messages.append({"role": "assistant", "content": content if "content" in dir() else ""})
        except Exception as e:
            last_error = str(e)

    return None


# ---------------------------------------------------------------------------
# Worker system prompt
# ---------------------------------------------------------------------------

_WORKER_SYSTEM = """\
You are OpalaCoder Worker — execute one atomic coding command using tools.

Your prompt will have this structure:
  TASK GOAL: <why this command exists>
  RELATED FILES (read these first): <comma-separated list>
  CONTEXT: <class names, IDs, APIs, contracts — everything you need without reading files>
  ---
  COMMAND: <the exact atomic action to perform>

CRITICAL: You MUST use the actual tool functions provided to you. Do NOT write JSON
describing what you would do. Do NOT produce a plan as text. CALL THE TOOLS DIRECTLY.

PREFERRED TOOLS:
- read_file       : token-aware read — call BEFORE editing any file
- edit_file       : atomic find-replace + auto-lint — prefer over read+write
- find_symbol     : symbol graph lookup for function/class analysis
- write_file      : only for new files or full rewrites
- run_command     : lint, compile, install — NEVER start servers

IMPROVEMENT LOOP:
edit_file returns lint errors automatically. On error: fix ONLY the specific
line shown, then call edit_file again. Do NOT rewrite the whole file.

RULES:
1. Read RELATED FILES before any edit — they are the source of truth for names and IDs.
2. After writing code, run a syntax check (python -m py_compile / node --check).
3. Call send_message ONCE when done, with a past-tense summary of changes made.
4. NEVER respond with raw JSON tool call descriptions — always invoke tools directly.
5. NEVER explain what you are about to do — just do it using tools.
"""


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@register_orchestrator("workflow")
class WorkflowOrchestratorStrategy(BaseOrchestratorStrategy):
    """Python-driven workflow orchestrator (specs3.md).

    Plan → Execute → Verify loop driven by the Python layer.
    Oracle calls use litellm with JSON mode, not response_schema.
    """

    def __init__(self, model: str | None = None):
        super().__init__(get_agent_model("orchestrator", model or DEFAULT_MODEL))

    # ------------------------------------------------------------------
    # Oracle system prompts
    # ------------------------------------------------------------------

    def _planner_system(self, project_context: str, session) -> str:
        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        core_memory = getattr(session, "core_memory", "") if session else ""
        memory_section = f"\nCore memory:\n{core_memory}\n" if core_memory else ""

        task_schema_example = json.dumps({
            "id": "t1",
            "goal": "Create style.css to style the calculator layout defined in index.html",
            "commands": [
                "Create style.css with CSS reset and .calculator flex wrapper",
                "Add .display, .buttons grid, and button variant classes (.btn-clear, .btn-number, .btn-operator, .btn-equals)"
            ],
            "related_files": ["index.html"],
            "context": (
                "index.html uses: .calculator (flex wrapper, 280px), .display (output, font-size 2rem), "
                ".buttons (4-column grid), .btn (base button), "
                ".btn-clear/.btn-number/.btn-operator/.btn-equals (color variants). "
                "Button IDs match their labels (e.g. id='add', id='7')."
            ),
            "depends_on": []
        }, indent=2)

        return f"""\
You are a software task planner for the project at `{proj_path}`.{memory_section}
Break the user request into focused, fully self-contained IMPLEMENTATION tasks.

IMPORTANT: Workers executing these tasks share NO memory and have NO access to each other's output.
Every task description must be 100% self-contained. Include all context a worker needs to act correctly.

Output ONLY valid JSON — no prose, no markdown fences:
{{"tasks": [<task>, ...]}}

Each task MUST follow this exact schema:
{task_schema_example}

Field rules:
- id: short unique identifier (t1, t2, ...)
- goal: one sentence — what this task achieves and WHY (e.g. "to style the HTML defined in index.html")
- commands: ordered list of atomic steps; each step is a separate worker action
  * Be concrete: "Add class .btn-login with display:flex, background:#e94560 to style.css"
  * NOT vague: "style the button"
- related_files: files the worker MUST read before acting (source of truth for class names, IDs, APIs)
  * CSS/JS tasks MUST list the HTML or source file that defines the selectors/IDs being used
- context: operational detail the worker needs WITHOUT reading files:
  * For CSS: list every class/ID from the HTML that will be styled
  * For JS: list every element ID, event type, and function contract
  * For Python: list function signatures, return types, imports needed
- depends_on: list of task ids that must complete before this one (empty list if none)

Ordering rules:
- Tasks that produce files another task depends on MUST come first.
- Use depends_on to express explicit ordering when needed.

Hard rules:
- The user request is COMPLETE — implement it directly, never ask for clarification.
- NEVER create tasks like "gather requirements", "clarify scope", or "ask the user".
- Every task MUST be a concrete file action (create, edit, run).
- If the request is vague, choose sensible defaults and implement them.
"""

    def _verifier_system(self, project_context: str) -> str:
        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        correction_example = json.dumps({
            "id": "c1",
            "goal": "Add missing .btn-equals selector to style.css",
            "commands": ["Add .btn-equals {{ background:#e94560; color:#fff; }} to the end of style.css"],
            "related_files": ["style.css", "index.html"],
            "context": "index.html has a button with class btn-equals and id='equals'. style.css already has .btn-clear and .btn-number but is missing .btn-equals.",
            "depends_on": []
        }, indent=2)

        return f"""\
You are a code reviewer for the project at `{proj_path}`.
You will receive the user request, the worker reports, AND the ACTUAL FILE CONTENTS
written to disk. Base your verdict on the real file contents — not on the worker's
self-reported summary.

Rules:
- Mark done=true ONLY if the real files satisfy every requirement in the user request.
- If a file is missing, empty, or incomplete, mark done=false and describe exactly what is wrong.
- Each correction task MUST follow the full task schema (same schema as planning tasks).
- Do NOT mark done=true just because the worker said it finished.

If done, output ONLY:
{{"done": true, "summary": "Past-tense summary of what was actually found in the files.", "corrections": []}}

If corrections needed, output ONLY:
{{"done": false, "summary": "What is still missing or wrong in the actual files.", "corrections": [<task>]}}

Each correction task schema:
{correction_example}
"""

    # ------------------------------------------------------------------
    # Planning phase (human-in-the-loop)
    # ------------------------------------------------------------------

    async def _plan_and_refine(self, user_request: str, history: str, session, store) -> str:
        """Generate a natural-language plan, show it to the user, save plan.md,
        and let the user refine it or press Enter to approve.
        Raises T.UserCancelled if the user types /cancel.
        """
        import os as _os

        T.section("Phase 1 — Implementation Overview")
        panorama_text = await generate_panorama(user_request, self.model, history=history)

        T.section("Phase 2 — Plan Refinement")
        approved_plan = await refine_plan(user_request, panorama_text, self.model, session, store)

        project_path = getattr(session, "project_path", ".") or "."
        plan_file_path = _os.path.join(project_path, "plan.md")
        try:
            _os.makedirs(project_path, exist_ok=True)
            with open(plan_file_path, "w", encoding="utf-8") as f:
                f.write(approved_plan)
        except Exception as e:
            T.warning(f"Could not save plan.md: {e}")

        return approved_plan

    # ------------------------------------------------------------------
    # Worker execution (specs3 #4 escalation on failure)
    # ------------------------------------------------------------------

    async def _run_worker(
        self,
        task: Task,
        project_context: str,
        llm_kwargs: dict,
        sub_hb: int,
        debug: bool,
    ) -> str:
        AGENT_PROGRESS.last_tool = f"Worker → {task.id}"
        AGENT_PROGRESS.last_args = task.goal[:70]

        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        # Build the context preamble injected into every command prompt
        related = ", ".join(task.related_files) if task.related_files else "none"
        context_block = (
            f"TASK GOAL: {task.goal}\n"
            f"RELATED FILES (read these first): {related}\n"
            f"CONTEXT:\n{task.context}\n"
            f"---\n"
        )

        system = _WORKER_SYSTEM + f"\nWork EXCLUSIVELY inside `{proj_path}`.\n"
        worker_kwargs = {**llm_kwargs, "reasoning_effort": "none"}

        async def _run_command(cmd_index: int, command: str, model: str) -> str:
            prompt = context_block + f"COMMAND: {command}"
            tools = get_workflow_tools()
            agent = LLMAgentBlock(
                name=f"worker_{task.id}_c{cmd_index}",
                system_prompt=system,
                model=model,
                tools=tools,
                litellm_kwargs=worker_kwargs,
                max_iterations=None,
                max_tool_calls=sub_hb * 3,
                debug=debug,
            )
            try:
                T.debug_worker_start(f"{task.id}[{cmd_index}]", command, model)
                T.debug_worker_project_path(task.id, get_project_path())
                out = await agent.run(AgentInput(prompt=prompt))
                result_text = out.response or "(no output)"
                T.debug_worker_tool_calls(f"{task.id}[{cmd_index}]", out.tool_calls_made)
                T.debug_worker_result(f"{task.id}[{cmd_index}]", result_text)
                return result_text
            except Exception as e:
                T.debug_worker_result(f"{task.id}[{cmd_index}]", f"[ERROR]: {e}")
                return f"[ERROR]: {e}"

        _failure = ("error", "failed", "unable to", "could not", "[error]")

        async def _try_command(cmd_index: int, command: str) -> str:
            result = await _run_command(cmd_index, command, self.model)
            # specs3 #4 — escalate on failure signals
            if any(s in result.lower() for s in _failure):
                try:
                    from .config import ALTERNATIVE_MODEL
                    from .api_keys import ensure_api_key
                    if self.model != ALTERNATIVE_MODEL and ensure_api_key(ALTERNATIVE_MODEL):
                        AGENT_PROGRESS.last_tool = f"Escalating → {ALTERNATIVE_MODEL[:20]}"
                        alt = await _run_command(cmd_index, command, ALTERNATIVE_MODEL)
                        if not any(s in alt.lower() for s in _failure):
                            result = alt
                except Exception:
                    pass
            return result

        # Execute commands sequentially; accumulate results
        command_results: list[str] = []
        for i, command in enumerate(task.commands):
            AGENT_PROGRESS.last_tool = f"Worker {task.id} [{i+1}/{len(task.commands)}]"
            AGENT_PROGRESS.last_args = command[:70]
            res = await _try_command(i, command)
            command_results.append(f"[cmd{i+1}] {res}")

        return "\n".join(command_results)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    async def run(self, user_request: str, history: str, **kwargs) -> str:
        session = kwargs.get("session")
        store = kwargs.get("store")

        project_context = (
            session.context_header()
            if session and hasattr(session, "context_header")
            else ""
        )

        llm_kwargs = get_agent_llm_kwargs("orchestrator")
        max_hb_config = get_agent_max_heartbeats("orchestrator", 20)
        scale_factor = get_agent_heartbeats_scale_factor("orchestrator", 2.0)

        if max_hb_config == "auto":
            max_hb_config = 50
        max_hb = int(max_hb_config)
        debug = get_agent_debug("orchestrator", False)
        sub_hb = max(10, int(max_hb * scale_factor))

        AGENT_PROGRESS.heartbeat = 0
        AGENT_PROGRESS.max_heartbeats = max_hb
        AGENT_PROGRESS.last_tool = "Initializing…"
        AGENT_PROGRESS.last_args = ""
        AGENT_PROGRESS.start_time = time.monotonic()

        # ── Human-in-the-loop planning phase ──────────────────────────
        hist_text = ""
        for msg in (session.history[-10:-1] if session and hasattr(session, "history") else []):
            role = "Assistant" if msg["role"] == "assistant" else "User"
            hist_text += f"{role}: {msg['content']}\n"

        approved_plan = ""
        if session and store:
            approved_plan = await self._plan_and_refine(user_request, hist_text, session, store)
        # ──────────────────────────────────────────────────────────────

        # Set project context AFTER planning so _PROJECT_PATH is correct for workers
        from .tools import set_project_context
        if session and store:
            set_project_context(session, store)

        # Build (or incrementally refresh) the code index for this project
        try:
            CODE_INDEX.set_project(get_project_path())
            stats = CODE_INDEX.build()
            T.debug_oracle("code_index", 0, f"Index ready: {stats}")
        except Exception as _idx_err:
            T.debug_oracle("code_index", 0, f"Index build skipped: {_idx_err}")

        planner_sys = self._planner_system(project_context, session)
        verifier_sys = self._verifier_system(project_context)

        # Project snapshot fetched once — used to prime oracle without tools
        snapshot = _project_snapshot()

        heartbeats_used = 0
        all_task_results: list[dict] = []
        final_summary = ""

        def _save_intermediate(tag: str, content: str) -> None:
            """Log intermediate orchestration events — does NOT write to chat history
            to avoid injecting invalid roles into LiteLLM message sequences."""
            T.debug_oracle(f"intermediate_{tag}", 0, f"[{tag.upper()}] {content[:300]}")

        async def _orchestration_loop():
            nonlocal heartbeats_used, final_summary

            plan_section = f"\nApproved plan (user-reviewed):\n{approved_plan}\n" if approved_plan else ""
            planning_prompt = (
                f"Project files:\n{snapshot}\n\n"
                f"Conversation history:\n{history}\n"
                f"{plan_section}\n"
                f"User request:\n{user_request}"
            )

            while heartbeats_used < max_hb:

                # ── Phase 1: Plan ──────────────────────────────────────────
                AGENT_PROGRESS.last_tool = "Planner (reflection)"
                AGENT_PROGRESS.last_args = ""

                if all_task_results:
                    results_block = "\n".join(
                        f"[{r['id']}] {r['result'][:300]}" for r in all_task_results
                    )
                    planning_prompt = (
                        f"Project files:\n{snapshot}\n\n"
                        f"User request:\n{user_request}\n\n"
                        f"Previous task results:\n{results_block}\n\n"
                        "Plan only the remaining or correction tasks."
                    )

                plan: PlanOutput | None = await _oracle(
                    PlanOutput, planner_sys, planning_prompt,
                    model=self.model, llm_kwargs=llm_kwargs,
                )

                if plan is None or not plan.tasks:
                    final_summary = (
                        "(Planner could not produce a valid task plan after "
                        f"{MAX_REFLECT_RETRIES} reflection attempts.)"
                    )
                    break

                # ── Phase 2: Execute ───────────────────────────────────────
                _save_intermediate("plan", f"Tasks: {[t.id for t in plan.tasks]}")
                for task in plan.tasks:
                    if heartbeats_used >= max_hb:
                        break
                    result = await _run_worker_safe(task)
                    all_task_results.append({"id": task.id, "result": result})
                    _save_intermediate("task", f"[{task.id}] {result[:500]}")
                    heartbeats_used += 1
                    AGENT_PROGRESS.heartbeat = heartbeats_used

                # ── Phase 3: Verify ────────────────────────────────────────
                AGENT_PROGRESS.last_tool = "Verifier (reflection)"
                AGENT_PROGRESS.last_args = ""

                results_block = "\n".join(
                    f"[{r['id']}] {r['result'][:400]}" for r in all_task_results
                )
                file_contents = _read_project_files_for_verify()
                verify_prompt = (
                    f"User request:\n{user_request}\n\n"
                    f"Worker reports (self-reported):\n{results_block}\n\n"
                    f"Actual file contents on disk:\n{file_contents}"
                )
                verify: VerifyOutput | None = await _oracle(
                    VerifyOutput, verifier_sys, verify_prompt,
                    model=self.model, llm_kwargs=llm_kwargs,
                )

                if verify is None:
                    final_summary = "(Verifier could not produce a valid result.)"
                    break

                if verify.done:
                    final_summary = verify.summary
                    _save_intermediate("verify", f"DONE: {verify.summary[:500]}")
                    break

                if not verify.corrections:
                    final_summary = verify.summary or "(No corrections specified.)"
                    break

                # Execute correction tasks directly, then re-verify on next loop
                # Cap at 2 corrections per cycle to preserve heartbeat budget
                for task in verify.corrections[:2]:
                    if heartbeats_used >= max_hb:
                        break
                    result = await _run_worker_safe(task)
                    all_task_results.append({"id": task.id, "result": result})
                    heartbeats_used += 1
                    AGENT_PROGRESS.heartbeat = heartbeats_used

            if not final_summary:
                if heartbeats_used >= max_hb:
                    final_summary = "(Heartbeat budget exhausted — work may be incomplete.)"
                else:
                    final_summary = "(Orchestration ended without a final summary.)"

        async def _run_worker_safe(task: Task) -> str:
            try:
                return await self._run_worker(
                    task, project_context, llm_kwargs, sub_hb, debug
                )
            except Exception as e:
                return f"[ERROR executing {task.id}]: {e}"

        loop_task = asyncio.create_task(_orchestration_loop())

        with Live(
            _build_progress_panel(AGENT_PROGRESS, max_hb),
            console=T.console,
            refresh_per_second=4,
            transient=False,
        ) as live:
            AGENT_PROGRESS.live_context = live
            while not loop_task.done():
                if live.is_started:
                    live.update(_build_progress_panel(AGENT_PROGRESS, max_hb))
                await asyncio.sleep(0.25)
            AGENT_PROGRESS.live_context = None
            if not live.is_started:
                live.start()
            live.update(_build_progress_panel(AGENT_PROGRESS, max_hb))

        exc = loop_task.exception()
        if exc:
            return f"Workflow orchestrator error: {exc}"

        return _deduplicate_response(final_summary)
