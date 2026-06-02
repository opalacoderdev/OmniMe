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

from pydantic import BaseModel, ValidationError, field_validator
from rich.live import Live

from agenticblocks.blocks.llm.agent import AgentInput, LLMAgentBlock, _get_shared_router as _llm_router

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
    review_only: bool = False    # True = task only reads/inspects, no file writes required
    status: str = "pending"      # pending | done | failed
    failure_count: int = 0       # incremented each time reviewer says done=False
    oracle_failure_count: int = 0  # incremented when reviewer oracle itself fails (format error)

    @field_validator("context", mode="before")
    @classmethod
    def _coerce_context(cls, v):
        if not isinstance(v, str):
            return json.dumps(v)
        return v

    @field_validator("commands", mode="before")
    @classmethod
    def _coerce_commands(cls, v):
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # Model emitted a structured object instead of a plain string command.
                # Extract the most descriptive text field available, or serialize the dict.
                for key in ("action", "goal", "description", "step", "command", "text"):
                    if key in item and isinstance(item[key], str):
                        result.append(item[key])
                        break
                else:
                    result.append(json.dumps(item))
            else:
                result.append(str(item))
        return result


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
    # CSS/JS tasks that *edit/add to* existing files must list those files in related_files
    # so the worker can read the current state before modifying.
    # Tasks that *create* a new file from scratch are exempt — nothing to read yet.
    goal_lower = task.goal.lower()
    cmd_text = " ".join(task.commands).lower()
    combined = goal_lower + cmd_text
    is_css_js_task = any(ext in combined for ext in (".css", ".js", ".ts"))
    is_create_task = any(w in goal_lower for w in ("create", "add", "new", "write", "generate", "build"))
    is_edit_task = any(w in goal_lower for w in ("edit", "update", "modify", "fix", "refactor", "change", "implement", "add to", "connect", "wire", "integrate"))
    if is_css_js_task and is_edit_task and not is_create_task and not task.related_files:
        errors.append(
            f"task '{task.id}': 'related_files' is empty for a CSS/JS edit task — "
            "list the files that must be read before modifying (the JS/CSS file being edited, "
            "and the HTML file that defines the IDs/classes being targeted)."
        )
    return "\n".join(errors) if errors else None


class PlanOutput(BaseModel):
    tasks: list[Task]


class VerifyOutput(BaseModel):
    done: bool
    summary: str              # past-tense if done; what's missing otherwise
    corrections: list[Task] = []  # new tasks to add to the plan when done=False; optional when done=True


MAX_TASK_FAILURES = 3        # abort plan after this many failed review cycles per task
MAX_REVIEWER_ORACLE_FAILS = 2  # skip reviewer and treat task as done after this many oracle failures


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

    Two independent retry budgets:
    - MAX_REFLECT_RETRIES: for JSON parse / Pydantic schema failures (LLM format errors)
    - MAX_SEMANTIC_RETRIES: for PlanOutput semantic validation (empty context, missing files, etc.)
    Keeping them separate prevents semantic feedback from eating JSON-format retry budget.
    """
    MAX_SEMANTIC_RETRIES = 3
    kwargs = {**llm_kwargs, "response_format": {"type": "json_object"}}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    last_error = ""
    semantic_attempts = 0

    for attempt in range(MAX_REFLECT_RETRIES):
        if attempt > 0:
            # Only count as plan retry when it's a real format failure, not a semantic one
            AGENT_PROGRESS.record_plan_retry(attempt)
            fields = {k: str(v.annotation) for k, v in schema.model_fields.items()}
            messages.append({"role": "user", "content": (
                f"[GUARDRAIL — attempt {attempt + 1}/{MAX_REFLECT_RETRIES}]: "
                f"{last_error}. "
                f"Required JSON schema: {json.dumps(fields)}. "
                f"Output ONLY a valid JSON object — no prose, no markdown."
            )})

        try:
            resp = await _llm_router(model).acompletion(
                model=model, messages=messages, **kwargs
            )
            msg = resp.choices[0].message
            content = (msg.content or "").strip()
            T.debug_oracle(schema.__name__, attempt, content)
            # Strip markdown fences if present
            if content.startswith("```"):
                content = re.sub(r"^```[a-z]*\n?", "", content)
                content = re.sub(r"\n?```$", "", content)
            data = json.loads(content)
            result = schema.model_validate(data)
            # Semantic validation for PlanOutput: tasks must be self-contained.
            # Uses a separate retry budget so these don't consume JSON-format retries.
            if isinstance(result, PlanOutput):
                feedback = [f for t in result.tasks if (f := _validate_task(t))]
                if feedback and semantic_attempts < MAX_SEMANTIC_RETRIES:
                    semantic_attempts += 1
                    semantic_error = (
                        "Plan tasks are incomplete:\n" + "\n".join(feedback) +
                        "\nFix ALL flagged tasks before returning the plan."
                    )
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": (
                        f"[SEMANTIC CHECK — attempt {semantic_attempts}/{MAX_SEMANTIC_RETRIES}]: "
                        f"{semantic_error}"
                    )})
                    # Retry the LLM call without consuming the format-retry budget
                    try:
                        resp2 = await _llm_router(model).acompletion(
                            model=model, messages=messages, **kwargs
                        )
                        content2 = (resp2.choices[0].message.content or "").strip()
                        if content2.startswith("```"):
                            content2 = re.sub(r"^```[a-z]*\n?", "", content2)
                            content2 = re.sub(r"\n?```$", "", content2)
                        data2 = json.loads(content2)
                        result2 = schema.model_validate(data2)
                        feedback2 = [f for t in result2.tasks if (f := _validate_task(t))]
                        if not feedback2:
                            return result2
                        # Still invalid — append and fall through to next format attempt
                        messages.append({"role": "assistant", "content": content2})
                        last_error = "Plan tasks are still incomplete after semantic fix: " + "; ".join(feedback2)
                    except Exception:
                        pass  # fall through to next format attempt
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
            T.debug_oracle_error(schema.__name__, attempt, last_error, "")

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
                    use the `line` param when old_str appears more than once
                    to DELETE a line: old_str=<full line>, new_str="", line=<line number>
- find_symbol     : symbol graph lookup for function/class analysis
- write_file      : only for new files or full rewrites
- run_command     : lint, compile, install — NEVER start servers

SKILL TOOLS (if available): language-specific bug detectors injected from the active skill.
Call them at the start of any fix/refactor command to know what is already broken.
When a skill tool returns [CONTRACT ERROR] with "FIX REQUIRED IN HTML:", you MUST
edit the HTML file at the specified line — do NOT modify the JS file.

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

    def _planner_system(self, project_context: str, session, skill_tool_names: list[str] = None) -> str:
        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        # core_memory is NOT injected here — the enricher (chat agent) already
        # selected the relevant facts and passed them via user_request as
        # "Memory Context (from chat agent)". Dumping the raw core_memory into
        # the system prompt would flood small-context models with stale noise.
        memory_section = ""

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
            "depends_on": [],
            "review_only": False
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
- commands: ordered list of atomic steps; each step is a PLAIN TEXT STRING describing what to do
  * CRITICAL: every element MUST be a string. NEVER put a JSON object or dict inside commands.
  * Be concrete: "Add class .btn-login with display:flex, background:#e94560 to style.css"
  * NOT vague: "style the button"
  * Each command is a plain text instruction string — NEVER a JSON object
- related_files: files the worker MUST read before acting (source of truth for class names, IDs, APIs)
  * CSS/JS tasks MUST list the HTML or source file that defines the selectors/IDs being used
- context: operational detail the worker needs WITHOUT reading files:
  * For CSS: list every class/ID from the HTML that will be styled
  * For JS: list every element ID, event type, and function contract
  * For Python: list function signatures, return types, imports needed
- depends_on: list of task ids that must complete before this one (empty list if none)
- review_only: true if the task ONLY reads, inspects, or runs diagnostic tools — no file writes expected.
  Set to false for any task that creates or modifies files.

Ordering rules:
- Tasks that produce files another task depends on MUST come first.
- Use depends_on to express explicit ordering when needed.

Hard rules:
- The user request is COMPLETE — implement it directly, never ask for clarification.
- NEVER create tasks like "gather requirements", "clarify scope", or "ask the user".
- Every task MUST be a concrete file action (create, edit, run).
- If the request is vague, choose sensible defaults and implement them.
- For redeclaration errors (SyntaxError: redeclaration / already declared): the fix is to
  DELETE the duplicate declaration line using edit_file with new_str="". Never change const→let or
  let→var — that keeps the duplicate. Command must be: "delete line N using edit_file(old_str=<line content>, new_str='', line=N)".
""" + (
            f"\nAvailable skill tools (workers have these as callable functions):\n"
            + "\n".join(f"- {name}" for name in skill_tool_names)
            + "\nFor fix/refactor tasks, the first command MUST call the relevant skill tool on the target file.\n"
            "\nCRITICAL — when the planning prompt contains a skill tool pre-scan with [CONTRACT ERROR] or [FIX REQUIRED IN ...]:\n"
            "- Create tasks ONLY for the files explicitly named in 'FIX REQUIRED IN <file>'.\n"
            "- Do NOT create tasks for files the scan does not flag. If the scan says JS is correct, do NOT add a JS task.\n"
            "- One bug = one fix task in the exact file named. Do not invent follow-up refactoring tasks.\n"
            if skill_tool_names else ""
        )

    def _planner_system_bugfix(self, project_context: str, session, skill_tool_names: list[str] = None) -> str:
        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        task_schema_example = json.dumps({
            "id": "t1",
            "goal": "Fix the divide-by-zero error in calculator.py line 42",
            "commands": [
                "Read calculator.py lines 38-50 to confirm the buggy division expression",
                "Edit calculator.py: add guard `if divisor == 0: return None` before line 42"
            ],
            "related_files": ["calculator.py"],
            "context": (
                "Bug is in function `divide(a, b)` at line 42: `return a / b` raises ZeroDivisionError "
                "when b=0. Fix must return None (or raise ValueError) without changing function signature."
            ),
            "depends_on": [],
            "review_only": False
        }, indent=2)

        return f"""\
You are a software bugfix planner for the project at `{proj_path}`.
You have received VECTOR CONTEXT: ranked code chunks most semantically similar to the bug report.
Use them as the primary source of truth for locating the defect.

Break the fix into focused, fully self-contained IMPLEMENTATION tasks.

IMPORTANT: Workers share NO memory and have NO access to each other's output.
Every task description must be 100% self-contained.

Output ONLY valid JSON — no prose, no markdown fences:
{{"tasks": [<task>, ...]}}

Each task MUST follow this exact schema:
{task_schema_example}

Field rules:
- id: short unique identifier (t1, t2, ...)
- goal: one sentence — what specific bug this task fixes and in which file/function
- commands: ordered list of atomic steps; each step is a PLAIN TEXT STRING
  * CRITICAL: every element MUST be a string. NEVER put a JSON object or dict inside commands.
  * The FIRST command MUST be a string like: "Read script.js lines 38-50 to inspect the buggy section"
  * Be concrete about line numbers and exact expressions when known from vector context
- related_files: only files mentioned in the vector context or directly implicated by the bug
- context: exact details from vector context the worker needs (function names, line ranges, expressions)
- depends_on: task ids that must complete first (usually empty for bugfixes)
- review_only: true if the task ONLY reads, inspects, or runs diagnostic tools — no file writes expected.
  Set to false for any task that creates or modifies files.

Hard rules:
- ONLY modify files present in the vector context unless the bug clearly propagates to another file.
- Do NOT create new files unless explicitly required by the fix.
- Do NOT refactor, rename, or clean up code beyond what is needed to fix the reported bug.
- Never add tasks like "gather requirements" or "ask the user".
- The user request is COMPLETE — fix it directly.
""" + (
            f"\nAvailable skill tools (workers have these as callable functions):\n"
            + "\n".join(f"- {name}" for name in skill_tool_names)
            + "\nFor fix tasks, the first command MUST call the relevant skill tool on the target file.\n"
            if skill_tool_names else ""
        )

    def _reviewer_system(self, project_context: str) -> str:
        """System prompt for the planner-review oracle.

        Called after each task completes. Receives the current plan (JSON),
        the worker feedback for one task, and the actual file contents.
        Returns VerifyOutput: done=True marks the task done; done=False adds
        correction tasks to the plan.
        """
        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        correction_example = json.dumps({
            "id": "c1",
            "goal": "Add missing .btn-equals selector to style.css",
            "commands": ["Add .btn-equals { background:#e94560; color:#fff; } to the end of style.css"],
            "related_files": ["style.css", "index.html"],
            "context": (
                "index.html has a button with class btn-equals and id='equals'. "
                "style.css already has .btn-clear and .btn-number but is missing .btn-equals."
            ),
            "depends_on": [],
            "status": "pending",
            "failure_count": 0,
        }, indent=2)

        return f"""\
You are a task reviewer for the project at `{proj_path}`.
You receive: the current task (from the plan), the worker's result, the actual
file contents written to disk, and lint results for all modified files.

Your job: decide whether THIS SPECIFIC TASK is done.

Rules:
- If the lint results show ANY syntax error, you MUST set done=false — a file with
  syntax errors is broken regardless of what the worker reported.
- If the worker result contains [CONTRACT ERROR] lines, read them carefully.
  A [CONTRACT ERROR] with "FIX REQUIRED IN HTML:" means the HTML attribute was NOT
  changed. Check the actual HTML file content below — if the attribute is still wrong
  (e.g. data-value='-' instead of data-action='subtract'), set done=false and generate
  a correction task that edits the HTML file at the exact line number specified.
- Set done=true only if lint is clean AND the file contents satisfy the task's goal.
- Set done=false only if something is concretely wrong or missing in the actual files.
- Do NOT invent problems. Do NOT require perfection beyond the task goal.
- If done=false, return exactly one correction task describing what remains.
- The correction task MUST follow the full task schema.

If done, output ONLY:
{{"done": true, "summary": "Past-tense: what was verified in the files.", "corrections": []}}

If not done, output ONLY:
{{"done": false, "summary": "Exactly what is wrong or missing.", "corrections": [<correction_task>]}}

Correction task schema:
{correction_example}
"""

    # ------------------------------------------------------------------
    # Planning phase (human-in-the-loop)
    # ------------------------------------------------------------------

    async def _plan_and_refine(self, user_request: str, history: str, session, store,
                               interactive: bool = True) -> str:
        """Generate a natural-language plan, show it to the user, save plan.md,
        and let the user refine it or press Enter to approve.
        Raises T.UserCancelled if the user types /cancel.

        When *interactive* is False (e.g. the implement-feature skill running its
        Level-3 script non-interactively), the panorama is auto-approved without
        prompting — there is no terminal to read from. The user still converses
        with the MemGPT orchestrator afterwards.
        """
        import os as _os

        T.section("Phase 1 — Implementation Overview")
        panorama_text = await generate_panorama(user_request, self.model, history=history)

        if interactive:
            T.section("Phase 2 — Plan Refinement")
            approved_plan = await refine_plan(user_request, panorama_text, self.model, session, store)
        else:
            approved_plan = panorama_text

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
        skill_tools: list = None,
    ) -> str:
        AGENT_PROGRESS.last_tool = f"Worker → {task.id}"
        AGENT_PROGRESS.last_args = task.goal[:70]

        proj_path = "."
        if project_context:
            m = re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = m.group(1).strip() if m else "."

        related = ", ".join(task.related_files) if task.related_files else "none"
        _root = Path(proj_path)
        _MAX_SNAPSHOT_BYTES = 4000

        def _build_file_snapshot() -> str:
            """Read related_files from disk right now — called before each command
            so every command sees the file state left by the previous command."""
            snapshots: list[str] = []
            total = 0
            for _rel in task.related_files:
                if total >= _MAX_SNAPSHOT_BYTES:
                    snapshots.append("...(remaining related files omitted — snapshot budget reached)")
                    break
                _p = _root / _rel if not Path(_rel).is_absolute() else Path(_rel)
                if not _p.exists():
                    _matches = list(_root.rglob(Path(_rel).name))
                    _p = _matches[0] if _matches else _p
                if _p.exists() and _p.is_file():
                    try:
                        _content = _p.read_text(encoding="utf-8", errors="replace")
                        _allowed = min(2000, _MAX_SNAPSHOT_BYTES - total)
                        _snippet = _content[:_allowed]
                        if len(_content) > _allowed:
                            _snippet += f"\n...(truncated, {len(_content)} bytes total — use read_file for full content)"
                        snapshots.append(f"### {_rel} (current state on disk)\n```\n{_snippet}\n```")
                        total += len(_snippet)
                    except Exception:
                        pass
            if not snapshots:
                return ""
            return (
                "\nCURRENT FILE STATE (read from disk right now — use this, not your training data):\n"
                + "\n".join(snapshots) + "\n"
            )

        system = _WORKER_SYSTEM + f"\nWork EXCLUSIVELY inside `{proj_path}`.\n"
        worker_kwargs = dict(llm_kwargs)  # already contains worker-specific settings

        async def _run_command(cmd_index: int, command: str, model: str) -> str:
            # Rebuild snapshot on every command — reflects edits made by previous commands.
            _snapshot_section = _build_file_snapshot()
            prompt = (
                f"TASK GOAL: {task.goal}\n"
                f"RELATED FILES (read these first): {related}\n"
                f"CONTEXT:\n{task.context}\n"
                f"{_snapshot_section}"
                f"---\n"
                f"COMMAND: {command}"
            )
            tools = get_workflow_tools(skill_tools=skill_tools)

            # Collect tool outputs via on_iteration so the reviewer sees actual errors.
            # on_iteration receives the full message history each time; track the
            # last-seen index to process only new messages each call.
            tool_outputs: list[str] = []
            tools_called: list[str] = []   # names of every tool invoked this command
            _seen_up_to: list[int] = [0]   # mutable cell for closure

            def _capture_iteration(iteration: int, messages: list) -> None:
                new_msgs = messages[_seen_up_to[0]:]
                _seen_up_to[0] = len(messages)
                for msg in new_msgs:
                    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                    tcs = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
                    if role == "assistant" and tcs:
                        for tc in tcs:
                            fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
                            tname = (fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)) if fn else None
                            if tname:
                                tools_called.append(tname)
                    if role == "tool" and content:
                        tool_outputs.append(str(content))

            agent = LLMAgentBlock(
                name=f"worker_{task.id}_c{cmd_index}",
                system_prompt=system,
                model=model,
                tools=tools,
                model_kwargs=worker_kwargs,
                max_iterations=None,
                max_tool_calls=sub_hb * 3,
                debug=debug,
                on_iteration=_capture_iteration,
                termination_tools=["send_message"],
            )
            T.debug_worker_start(f"{task.id}[{cmd_index}]", command, model)
            T.debug_worker_project_path(task.id, get_project_path())
            out = await agent.run(AgentInput(prompt=prompt))
            result_text = out.response or "(no output)"
            # Append deduplicated tool outputs so the reviewer sees actual errors
            if tool_outputs:
                seen_outputs: set[str] = set()
                unique_outputs: list[str] = []
                for o in tool_outputs:
                    if o not in seen_outputs:
                        seen_outputs.add(o)
                        unique_outputs.append(o)
                result_text = result_text + "\n\n[Tool outputs]\n" + "\n---\n".join(unique_outputs)

            # Annotate result with tools called so the reviewer has factual evidence.
            if tools_called:
                result_text += f"\n\n[Tools invoked: {', '.join(tools_called)}]"

            T.debug_worker_tool_calls(f"{task.id}[{cmd_index}]", len(tool_outputs))
            T.debug_worker_result(f"{task.id}[{cmd_index}]", result_text)
            return result_text

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
        intent: str = kwargs.get("intent", "newfeat")
        interactive: bool = kwargs.get("interactive", True)

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

        worker_llm_kwargs = get_agent_llm_kwargs("worker")
        worker_debug = get_agent_debug("worker", debug)

        # Set project context early so get_project_path() is correct for VCS and workers
        from .tools import set_project_context
        if session and store:
            set_project_context(session, store)

        AGENT_PROGRESS.heartbeat = 0
        AGENT_PROGRESS.max_heartbeats = max_hb
        AGENT_PROGRESS.tasks_done = 0
        AGENT_PROGRESS.tasks_total = 0
        AGENT_PROGRESS.last_tool = "Initializing…"
        AGENT_PROGRESS.last_args = ""
        AGENT_PROGRESS.start_time = time.monotonic()
        AGENT_PROGRESS.task_failures = 0
        AGENT_PROGRESS.worker_errors = 0
        AGENT_PROGRESS.lint_errors = 0
        AGENT_PROGRESS.plan_retries = 0
        AGENT_PROGRESS.recent_events = []

        # ── Human-in-the-loop planning phase ──────────────────────────
        # hist_text is intentionally empty: relevant context is already
        # embedded in user_request via the enricher (chat_agent Mode A) in cli.py.
        # Passing raw history here caused the planner to act on unrelated prior tasks.
        approved_plan = ""
        if session and store:
            approved_plan = await self._plan_and_refine(
                user_request, "", session, store, interactive=interactive
            )
        # ──────────────────────────────────────────────────────────────

        # Auto-checkpoint before any worker modifies files — enables /undo
        # Must run after set_project_context so get_project_path() is correct.
        # _vcs is kept alive so per-task checkpoints can be created inside the loop.
        _vcs = None
        try:
            from .vcs import get_vcs_strategy
            from .config import get_git_strategy
            _vcs = get_vcs_strategy(get_git_strategy(), get_project_path())
            _vcs.setup()
            _vcs.manual_commit("auto-checkpoint before plan execution")
        except Exception as _vcs_err:
            T.debug_oracle("vcs", 0, f"Auto-checkpoint failed: {_vcs_err}")

        # Build (or incrementally refresh) the code index for this project
        try:
            CODE_INDEX.set_project(get_project_path())
            stats = CODE_INDEX.build()
            T.debug_oracle("code_index", 0, f"Index ready: {stats}")
        except Exception as _idx_err:
            T.debug_oracle("code_index", 0, f"Index build skipped: {_idx_err}")

        # Load tools declared in active skills (plugin system)
        _project_path = get_project_path()
        # Plugin-tools (skill-declared `tools:`/`reviewer:`) were retired with the
        # skills-oriented refactor: skills now run their detectors explicitly via
        # Level-3 scripts (e.g. html-css-js → check_contracts.py), not through an
        # implicit worker-injected reviewer. No skill tools/reviewers are loaded.
        _skill_tool_names: list[str] = []

        _is_bugfix = intent == "bugfix"
        if _is_bugfix:
            planner_sys = self._planner_system_bugfix(project_context, session, _skill_tool_names or None)
        else:
            planner_sys = self._planner_system(project_context, session, _skill_tool_names or None)
        reviewer_sys = self._reviewer_system(project_context)

        # Project snapshot fetched once — used to prime oracle without tools
        snapshot = _project_snapshot()

        tasks_executed = 0
        final_summary = ""

        def _save_intermediate(tag: str, content: str) -> None:
            T.debug_oracle(f"intermediate_{tag}", 0, f"[{tag.upper()}] {content[:300]}")

        def _pending_tasks(plan: PlanOutput) -> list[Task]:
            """Return tasks that are pending and whose dependencies are all done."""
            done_ids = {t.id for t in plan.tasks if t.status == "done"}
            return [
                t for t in plan.tasks
                if t.status == "pending"
                and all(dep in done_ids for dep in t.depends_on)
            ]

        def _read_relevant_files(task: Task, max_bytes_per_file: int = 6000, max_total: int = 12000) -> str:
            """Read only the files listed in task.related_files for the reviewer.

            Hard cap on total bytes sent to the reviewer oracle to avoid context overflow.
            """
            root = Path(get_project_path())
            parts: list[str] = []
            seen: set[str] = set()
            total = 0
            candidates = list(task.related_files)
            # Also include files mentioned in commands/goal (heuristic)
            for text in [task.goal] + task.commands:
                for word in text.split():
                    w = word.strip("\"'(),")
                    if "." in w and not w.startswith(".") and w not in seen:
                        candidates.append(w)
            for rel in candidates:
                if rel in seen:
                    continue
                if total >= max_total:
                    parts.append("...(remaining files omitted — reviewer budget reached)")
                    break
                seen.add(rel)
                p = root / rel if not Path(rel).is_absolute() else Path(rel)
                if not p.exists():
                    matches = list(root.rglob(Path(rel).name))
                    p = matches[0] if matches else p
                if p.exists() and p.is_file():
                    try:
                        content = p.read_text(encoding="utf-8", errors="replace")
                        allowed = min(max_bytes_per_file, max_total - total)
                        snippet = content[:allowed]
                        if len(content) > allowed:
                            snippet += f"\n...(truncated, {len(content)} bytes total)"
                        rel_display = str(p.relative_to(root)) if root in p.parents or p.parent == root else rel
                        parts.append(f"### {rel_display}\n```\n{snippet}\n```")
                        total += len(snippet)
                    except Exception:
                        pass
            return "\n\n".join(parts) if parts else "(no relevant files found)"

        def _run_lint(task: Task) -> str:
            """Run syntax checkers on all related files and return a lint summary.

            Results are injected into the reviewer prompt as authoritative ground truth.
            A syntax error here means done=false regardless of what the worker reported.
            """
            import subprocess as _sp
            root = Path(get_project_path())
            results: list[str] = []
            seen: set[str] = set()
            candidates = list(task.related_files)
            for text in [task.goal] + task.commands:
                for word in text.split():
                    w = word.strip("\"'(),")
                    if "." in w and not w.startswith("."):
                        candidates.append(w)
            for rel in candidates:
                if rel in seen:
                    continue
                seen.add(rel)
                p = root / rel if not Path(rel).is_absolute() else Path(rel)
                if not p.exists():
                    matches = list(root.rglob(Path(rel).name))
                    p = matches[0] if matches else p
                if not p.exists() or not p.is_file():
                    continue
                suffix = p.suffix.lower()
                try:
                    if suffix in (".js", ".mjs", ".cjs"):
                        r = _sp.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=10)
                        results.append(f"{rel}: {'OK' if r.returncode == 0 else 'SYNTAX ERROR — ' + r.stderr.strip()}")
                    elif suffix in (".py",):
                        r = _sp.run(["python", "-m", "py_compile", str(p)], capture_output=True, text=True, timeout=10)
                        results.append(f"{rel}: {'OK' if r.returncode == 0 else 'SYNTAX ERROR — ' + r.stderr.strip()}")
                    elif suffix in (".ts", ".tsx"):
                        r = _sp.run(["npx", "--no-install", "tsc", "--noEmit", "--allowJs", str(p)], capture_output=True, text=True, timeout=15)
                        results.append(f"{rel}: {'OK' if r.returncode == 0 else 'ERROR — ' + r.stdout.strip()[:300]}")
                except Exception as _le:
                    results.append(f"{rel}: lint skipped ({_le})")
            if not results:
                return "(no lintable files found)"
            return "\n".join(results)

        _WRITE_TOOLS = {"edit_file", "write_file", "write_content_pos"}

        def _git_changed_files() -> list[str]:
            """Return files changed or added since the last shadow-git checkpoint.

            Uses 'git status --porcelain' so both modified (M) and new untracked (??)
            files are detected — 'git diff HEAD' misses newly created files.
            """
            if _vcs is None:
                return []
            from .vcs import _run_shadow_git
            res = _run_shadow_git("status --porcelain")
            if res.returncode != 0:
                return []
            changed: list[str] = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Porcelain format: XY filename (or XY -> filename for renames)
                parts = line.split(None, 1)
                if len(parts) == 2:
                    fname = parts[1].strip()
                    if " -> " in fname:
                        fname = fname.split(" -> ", 1)[1]
                    changed.append(fname.strip())
            return changed

        async def _review_task(task: Task, worker_result: str, plan: PlanOutput) -> VerifyOutput | None:
            """Deterministic pre-checks first; only call the LLM reviewer when needed."""

            # ── 1. Lint (authoritative) ────────────────────────────────────
            lint_summary = _run_lint(task)
            has_lint_error = "SYNTAX ERROR" in lint_summary or "ERROR —" in lint_summary

            if has_lint_error:
                T.debug_oracle("reviewer", 0, f"[AUTO-REJECT] {task.id}: lint failed")
                AGENT_PROGRESS.record_task_failure(task.id, f"lint error: {lint_summary[:120]}")
                return VerifyOutput(
                    done=False,
                    summary=f"Lint failed — syntax errors must be fixed before marking done.\n{lint_summary}",
                    corrections=[Task(
                        id=f"{task.id}_lint",
                        goal=f"Fix syntax errors reported by lint in {', '.join(task.related_files) or 'related files'}",
                        commands=[f"Run node --check / py_compile on the file and fix every syntax error reported: {lint_summary[:300]}"],
                        related_files=task.related_files,
                        context=task.context,
                        depends_on=[],
                    )],
                )

            # ── 2. Did the worker actually change any files? ───────────────
            changed_files = _git_changed_files()
            edit_errors = worker_result.lower().count("old_str not found")

            # Count tool invocations from the annotated footer
            invoked: set[str] = set()
            for line in worker_result.splitlines():
                if line.startswith("[Tools invoked:"):
                    names = line.removeprefix("[Tools invoked:").rstrip("]").split(",")
                    invoked.update(n.strip() for n in names)

            worker_called_write = bool(invoked & _WRITE_TOOLS)

            # Worker claimed to write but nothing changed on disk → hard reject
            if worker_called_write and not changed_files and edit_errors == 0:
                T.debug_oracle("reviewer", 0,
                    f"[AUTO-REJECT] {task.id}: edit_file called but no files changed on disk")
                AGENT_PROGRESS.record_task_failure(
                    task.id, "worker called write tool but no files changed on disk"
                )
                return VerifyOutput(
                    done=False,
                    summary=(
                        "Worker reported calling edit_file but no files changed on disk. "
                        "The old_str probably did not match exactly. "
                        "Read the file first, copy the exact text to replace, then call edit_file."
                    ),
                    corrections=[Task(
                        id=f"{task.id}_nochange",
                        goal=task.goal,
                        commands=[
                            f"Read {', '.join(task.related_files) or 'the relevant file'} first to get the exact current text, "
                            "then call edit_file with old_str copied verbatim from the file."
                        ],
                        related_files=task.related_files,
                        context=task.context,
                        depends_on=[],
                    )],
                )

            # Worker did not call any write tool and did not change any files → hard reject
            # Skip this check for review_only tasks — they are not expected to write anything.
            if not task.review_only and not worker_called_write and not changed_files and invoked:
                T.debug_oracle("reviewer", 0,
                    f"[AUTO-REJECT] {task.id}: no write tool, no files changed (invoked={sorted(invoked)})")
                AGENT_PROGRESS.record_task_failure(
                    task.id, "no file-writing tools called and no files changed"
                )
                return VerifyOutput(
                    done=False,
                    summary=(
                        f"Worker called no file-writing tools (invoked: {', '.join(sorted(invoked))}) "
                        "and no files changed on disk. Required code changes were never applied."
                    ),
                    corrections=[Task(
                        id=f"{task.id}_nowrite",
                        goal=task.goal,
                        commands=[
                            f"Read {', '.join(task.related_files) or 'the relevant file'} first, "
                            "then call edit_file to apply the required change. Do not just read — you must write."
                        ],
                        related_files=task.related_files,
                        context=task.context,
                        depends_on=[],
                    )],
                )

            # ── 3. Partial edit: some edit_file calls failed ───────────────
            edit_error_note = ""
            if edit_errors > 0:
                edit_error_note = (
                    f"\n[NOTE] {edit_errors} edit_file call(s) failed with 'old_str not found' — "
                    "those specific changes were NOT applied. Check whether the required change "
                    "is present in the file contents below.\n"
                )

            # ── 4. Changed-files summary for reviewer context ──────────────
            changed_note = ""
            if changed_files:
                changed_note = f"\n[Files changed on disk]: {', '.join(changed_files)}\n"

            # All checks passed — proceed to LLM reviewer
            # ── 5. Call LLM reviewer with factual context ──────────────────
            task_json = json.dumps(task.model_dump(), indent=2)
            file_contents = _read_relevant_files(task)

            worker_result_capped = worker_result[:2000]
            if len(worker_result) > 2000:
                worker_result_capped += f"\n...(truncated, {len(worker_result)} chars total)"

            review_prompt = (
                f"Task under review:\n{task_json}\n\n"
                f"Lint results (all clean — no syntax errors):\n{lint_summary}\n"
                f"{changed_note}"
                f"{edit_error_note}\n"
                f"Worker result:\n{worker_result_capped}\n\n"
                f"Relevant file contents on disk:\n{file_contents}"
            )
            AGENT_PROGRESS.last_tool = f"Reviewer → {task.id}"
            AGENT_PROGRESS.last_args = task.goal[:70]
            reviewer_kwargs = {**llm_kwargs, "max_tokens": 2048}
            return await _oracle(
                VerifyOutput, reviewer_sys, review_prompt,
                model=self.model, llm_kwargs=reviewer_kwargs,
            )

        async def _run_worker_safe(task: Task) -> str:
            try:
                result = await self._run_worker(
                    task, project_context, worker_llm_kwargs, sub_hb, worker_debug,
                )
                if result.lower().startswith("[error"):
                    AGENT_PROGRESS.record_worker_error(task.id, result)
                return result
            except Exception as e:
                import traceback as _tb
                full_tb = _tb.format_exc()
                AGENT_PROGRESS.record_worker_error(task.id, str(e))
                T.debug_oracle(f"worker_exception_{task.id}", 0, full_tb)
                return f"[ERROR executing {task.id}]: {e}"

        async def _orchestration_loop():
            nonlocal tasks_executed, final_summary

            # ── Phase 1: Initial plan ──────────────────────────────────────
            AGENT_PROGRESS.last_tool = "Planner (reflection)"
            plan_section = f"\nApproved plan (user-reviewed):\n{approved_plan}\n" if approved_plan else ""

            # Inject content of files explicitly mentioned in the request so the
            # planner can see the actual code rather than guessing from error messages.
            def _extract_file_snippets(request_text: str, max_bytes: int = 3000) -> str:
                import re as _re
                root = Path(get_project_path())
                mentioned = _re.findall(r'\b[\w/-]+\.(?:js|ts|py|css|html|json|jsx|tsx|md)\b', request_text)
                parts: list[str] = []
                seen: set[str] = set()
                for fname in mentioned:
                    if fname in seen:
                        continue
                    seen.add(fname)
                    matches = list(root.rglob(fname))
                    if not matches:
                        continue
                    p = matches[0]
                    try:
                        content = p.read_text(encoding="utf-8", errors="replace")
                        snippet = content[:max_bytes]
                        if len(content) > max_bytes:
                            snippet += f"\n...(truncated, {len(content)} bytes)"
                        rel = str(p.relative_to(root))
                        # Add line numbers to help planner reference specific lines
                        numbered = "\n".join(
                            f"{i+1:4d}  {l}" for i, l in enumerate(snippet.splitlines())
                        )
                        parts.append(f"### {rel}\n```\n{numbered}\n```")
                    except Exception:
                        pass
                return "\n\n".join(parts)

            file_snippets = _extract_file_snippets(user_request)

            file_section = ""
            if file_snippets:
                file_section = (
                    "\nRelevant file contents (read before planning):\n"
                    + file_snippets + "\n"
                )

            # ── bugfix: build vector index and retrieve relevant chunks ──
            vector_chunk_section = ""
            if _is_bugfix:
                try:
                    from .vector_index import set_vector_project
                    from .config import get_vector_config
                    vcfg = get_vector_config()
                    vidx = set_vector_project(get_project_path())
                    T.debug_oracle("vector_index", 0, "Building vector index…")
                    vstats = vidx.build(
                        embedding_model=vcfg["embedding_model"],
                        embedding_fallback=vcfg["embedding_fallback"],
                        chunk_size=vcfg["chunk_size"],
                        chunk_overlap=vcfg["chunk_overlap"],
                    )
                    T.debug_oracle("vector_index", 0, f"Vector index ready: {vstats}")
                    ranked = vidx.retrieve(
                        query=user_request,
                        top_k=vcfg["top_k"],
                        embedding_model=vcfg["embedding_model"],
                        embedding_fallback=vcfg["embedding_fallback"],
                    )
                    if ranked:
                        vector_chunk_section = (
                            "\nChunks most likely related to the bug (retrieved by semantic search — use as leads, not restrictions):\n"
                            + vidx.format_for_prompt(ranked)
                            + "\n"
                        )
                        T.debug_oracle("vector_index", 0, f"Retrieved {len(ranked)} chunks for bugfix planner")
                except Exception as _vidx_err:
                    T.debug_oracle("vector_index", 0, f"Vector retrieval skipped: {_vidx_err}")

            planning_prompt = (
                f"Project files:\n{snapshot}\n"
                f"{file_section}\n"
                f"{vector_chunk_section}"
                f"Conversation history:\n{history}\n"
                f"{plan_section}\n"
                f"User request:\n{user_request}"
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
                return

            _save_intermediate("plan", f"Tasks: {[t.id for t in plan.tasks]}")
            T.debug_oracle("plan", 0, json.dumps({"tasks": [t.model_dump() for t in plan.tasks]}, indent=2, ensure_ascii=False))
            AGENT_PROGRESS.tasks_total = len(plan.tasks)
            AGENT_PROGRESS.tasks_done = 0

            # ── Phase 2: Execute tasks one by one, review after each ───────
            while True:
                pending = _pending_tasks(plan)
                if not pending:
                    break
                if tasks_executed >= max_hb:
                    done_tasks = [t for t in plan.tasks if t.status == "done"]
                    skipped_tasks = [t for t in plan.tasks if t.status == "pending"]
                    done_line = (
                        f"Completed {len(done_tasks)} task(s): "
                        + "; ".join(t.goal[:80] for t in done_tasks)
                        if done_tasks else "No tasks completed."
                    )
                    skipped_lines = "\n".join(f"  • [{t.id}] {t.goal}" for t in skipped_tasks)
                    final_summary = (
                        f"{done_line}\n\n"
                        f"Skipped {len(skipped_tasks)} task(s) (task budget of {max_hb} exhausted):\n"
                        + skipped_lines
                    )
                    return

                task = pending[0]
                AGENT_PROGRESS.last_tool = f"Worker → {task.id}"
                AGENT_PROGRESS.last_args = task.goal[:70]

                # Checkpoint before the task runs so we can roll back if it needs
                # to be re-executed. Without this, a retry would attempt the same
                # edit_file old_str on a file already modified by the first run.
                _task_checkpoint_ok = False
                if _vcs is not None:
                    try:
                        ok, _ = _vcs.manual_commit(f"pre-task {task.id}: {task.goal[:60]}")
                        _task_checkpoint_ok = ok
                        T.debug_oracle("vcs", 0, f"Checkpoint created before {task.id}")
                    except Exception as _ck_err:
                        T.debug_oracle("vcs", 0, f"Per-task checkpoint failed: {_ck_err}")

                worker_result = await _run_worker_safe(task)
                T.debug_worker_result(task.id, worker_result)
                _save_intermediate("task", f"[{task.id}] {worker_result[:500]}")
                tasks_executed += 1

                # ── Phase 3: Review this task ──────────────────────────────
                review = await _review_task(task, worker_result, plan)
                T.debug_oracle(f"reviewer_{task.id}", 0, str(review))
                if review is None:
                    # Reviewer oracle could not produce valid JSON — this is a format
                    # failure, NOT a task failure. Count separately so it doesn't
                    # wrongly abort the plan after MAX_TASK_FAILURES.
                    task.oracle_failure_count += 1
                    AGENT_PROGRESS.record_task_failure(task.id, "reviewer oracle failed (format error)")
                    _save_intermediate("review", f"[{task.id}] reviewer oracle failed ({task.oracle_failure_count}/{MAX_REVIEWER_ORACLE_FAILS})")
                    if task.oracle_failure_count >= MAX_REVIEWER_ORACLE_FAILS:
                        # Give up trying to review this task; treat it as done so the
                        # plan can continue. Worker output is preserved on disk.
                        task.status = "done"
                        AGENT_PROGRESS.tasks_done += 1
                        _save_intermediate("review", f"[{task.id}] skipped review after {MAX_REVIEWER_ORACLE_FAILS} oracle failures — treated as done")
                    elif _task_checkpoint_ok and _vcs is not None:
                        # Roll back files to the pre-task state so the next retry
                        # starts from a clean slate (avoids old_str-not-found errors).
                        try:
                            _vcs.undo_last()
                            T.debug_oracle("vcs", 0, f"Rolled back {task.id} after oracle failure")
                        except Exception as _rb_err:
                            T.debug_oracle("vcs", 0, f"Rollback failed: {_rb_err}")
                elif review.done:
                    task.status = "done"
                    AGENT_PROGRESS.tasks_done += 1
                    _save_intermediate("review", f"[{task.id}] DONE: {review.summary[:300]}")
                else:
                    task.failure_count += 1
                    AGENT_PROGRESS.record_task_failure(task.id, review.summary)
                    _save_intermediate("review", f"[{task.id}] NOT DONE ({task.failure_count}/{MAX_TASK_FAILURES}): {review.summary[:300]}")

                    if task.failure_count >= MAX_TASK_FAILURES:
                        failed_goals = [
                            f"  • [{t.id}] {t.goal}" for t in plan.tasks
                            if t.status != "done"
                        ]
                        final_summary = (
                            f"The plan could not be completed after {MAX_TASK_FAILURES} attempts "
                            f"on task '{task.id}'.\n\n"
                            f"Worker last reported:\n{worker_result[:400]}\n\n"
                            f"Reviewer feedback:\n{review.summary}\n\n"
                            f"Unfinished tasks:\n" + "\n".join(failed_goals) + "\n\n"
                            "Please try rephrasing your request with more detail about "
                            "what exactly needs to change and in which file."
                        )
                        return

                    # Add correction tasks to the plan (with unique ids)
                    existing_ids = {t.id for t in plan.tasks}
                    for correction in review.corrections:
                        # Ensure unique id
                        base_id = correction.id
                        uid = base_id
                        counter = 1
                        while uid in existing_ids:
                            uid = f"{base_id}_{counter}"
                            counter += 1
                        correction.id = uid
                        existing_ids.add(uid)
                        # Correction depends on the failed task
                        if task.id not in correction.depends_on:
                            correction.depends_on = [task.id] + correction.depends_on
                        plan.tasks.append(correction)

                    # Mark failed task as done so corrections can proceed
                    task.status = "done"
                    AGENT_PROGRESS.tasks_done += 1
                    AGENT_PROGRESS.tasks_total = len(plan.tasks)

            # All tasks done
            done_tasks = [t for t in plan.tasks if t.status == "done"]
            skipped_tasks = [t for t in plan.tasks if t.status == "pending"]
            final_summary = (
                f"Completed {len(done_tasks)} task(s): "
                + "; ".join(t.goal[:80] for t in done_tasks)
            )
            if skipped_tasks:
                skipped_lines = "\n".join(f"  • [{t.id}] {t.goal}" for t in skipped_tasks)
                final_summary += (
                    f"\n\nSkipped {len(skipped_tasks)} task(s) (reviewer accepted earlier results as sufficient):\n"
                    + skipped_lines
                )
            _save_intermediate("done", final_summary)

        loop_task = asyncio.create_task(_orchestration_loop())

        with Live(
            _build_progress_panel(AGENT_PROGRESS, AGENT_PROGRESS.max_heartbeats),
            console=T.console,
            refresh_per_second=4,
            transient=False,
        ) as live:
            AGENT_PROGRESS.live_context = live
            while not loop_task.done():
                if live.is_started:
                    live.update(_build_progress_panel(AGENT_PROGRESS, AGENT_PROGRESS.max_heartbeats))
                await asyncio.sleep(0.25)
            AGENT_PROGRESS.live_context = None
            if not live.is_started:
                live.start()
            live.update(_build_progress_panel(AGENT_PROGRESS, AGENT_PROGRESS.max_heartbeats))

        exc = loop_task.exception()
        if exc:
            return f"Workflow orchestrator error: {exc}"

        return _deduplicate_response(final_summary)
