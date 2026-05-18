"""MemGPT-style autonomous orchestrator with real-time live progress panel."""

import asyncio
import logging
import time
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box

import abc


class _SuppressMockToolCallErrors(logging.Filter):
    """Suppress the non-fatal LiteLLM serialization error caused by MockToolCall objects."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "__pydantic_fields_set__" not in record.getMessage()


logging.getLogger("LiteLLM").addFilter(_SuppressMockToolCallErrors())

from agenticblocks.blocks.llm.memgpt_agent import MemGPTAgentBlock
from agenticblocks.blocks.llm.agent import AgentInput
from .tools import get_available_tools, AGENT_PROGRESS
from .config import get_agent_llm_kwargs, get_agent_model, get_agent_debug, DEFAULT_MODEL, get_agent_max_heartbeats
from . import terminal as T


class BaseOrchestratorStrategy(abc.ABC):
    def __init__(self, model: str):
        self.model = model

    @abc.abstractmethod
    async def run(self, user_request: str, history: str, **kwargs) -> str:
        """Execute the orchestration logic for the given user request."""
        pass


def _build_progress_panel(progress: object, max_hb: int) -> Panel:
    """Build a Rich Panel showing current agent activity."""
    hb = progress.heartbeat
    bar_filled = min(hb, max_hb)
    bar_empty = max(0, max_hb - bar_filled)
    bar = f"[cyan]{'█' * bar_filled}[/cyan][dim]{'░' * bar_empty}[/dim]"

    tool_color = {
        "write_file": "green",
        "write_content_pos": "green",
        "read_file": "blue",
        "read_content_pos": "blue",
        "get_file_overview": "blue",
        "get_project_overview": "magenta",
        "run_command": "yellow",
        "search_code": "magenta",
        "ask_human": "red",
        "send_message": "cyan",
    }.get(progress.last_tool, "white")

    tool_line = f"[bold {tool_color}]🔧 {progress.last_tool}[/bold {tool_color}]"
    if progress.last_args:
        tool_line += f"\n   [dim]↳ {progress.last_args}[/dim]"

    content = (
        f"[bold]Heartbeat:[/bold] {hb}/{max_hb}  {bar}\n"
        f"[bold]Elapsed:[/bold]   {progress.elapsed()}\n\n"
        f"{tool_line}"
    )
    return Panel(
        content,
        title="[bold cyan]🤖 Orchestrator Working[/bold cyan]",
        border_style="cyan",
        expand=False,
    )


class AutonomousOrchestratorStrategy(BaseOrchestratorStrategy):
    def __init__(self, model: str | None = None):
        super().__init__(get_agent_model("orchestrator", model or DEFAULT_MODEL))
        self.tools = get_available_tools()

    def _build_system_prompt(self, approved_plan: str = "", project_context: str = "") -> str:
        import re as _re

        proj_path = "."
        project_header = ""
        if project_context:
            _m = _re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = _m.group(1).strip() if _m else "."
            _n = _re.search(r"PROJECT:\s*(.+?)\s*\|", project_context)
            proj_name = _n.group(1).strip() if _n else proj_path
            project_header = f"""
## PROJECT CONTEXT
Name : {proj_name}
Path : {proj_path}

You are working EXCLUSIVELY inside this project. Every file you read, write, or execute
must live under `{proj_path}`. Never touch files outside this directory.
"""

        plan_section = ""
        if approved_plan:
            plan_section = f"""
## APPROVED PLAN
The user reviewed and approved this plan. **Execute every step now — do not re-describe the plan.**
Use your tools to implement it fully before calling `send_message`.

{approved_plan}
"""

        return f"""You are OpalaCoder — an autonomous software-engineering agent embedded inside a project workspace.
{project_header}
## FIRST ACTION — always
Before doing anything else, call `get_project_overview` to understand the current state of the project:
its files, structure, and technology stack. Use that snapshot to make every decision that follows.
{plan_section}
## YOUR MISSION
Implement coding tasks autonomously within the project. This includes creating new features, fixing bugs,
refactoring, and updating any existing code inside the project directory.

## RULES
1. **Project-first**: Every action must reference the project. Read existing files before rewriting them. Use `get_file_overview` to understand a file's structure before making targeted edits.
   Extend what is already there unless a full rewrite is explicitly requested.
2. **ACT, don't ask**: Create directories, write files, run `npm install`, `pip install`, or any standard
   dev command without asking for permission.
3. **Fix bugs autonomously**: read the relevant file → identify the problem → fix in place.
   Do NOT recreate from scratch unless the file is irreparably broken.
4. **Never start servers**: Do NOT run `npm start`, `npm run dev`, `flask run`, or any long-running process.
5. **Verify your work**: After writing code, run a quick syntax/lint check (e.g. `node --check file.js`,
   `python -m py_compile file.py`).
6. **Use ask_human ONLY** for genuinely dangerous or irreversible operations (`rm -rf`, `sudo`,
   credentials, files outside the project).
7. **Internal Version Control**: You may have access to git tools (if allowed by the user strategy) that operate on an internal "Shadow Git".
   - If available, use `git_diff` to review your code changes.
   - If available, use `git_commit` to save milestones of your work logically.
   - You can use `run_command` with `git --git-dir=.opalacoder/.git --work-tree=. checkout <file>` to revert mistakes.
8. **Report ONCE — but only after finishing**: Call `send_message` **exactly once**, and only after
   you have fully completed every step of the plan (all files written, commands run, verifications done).
   NEVER call `send_message` to describe what you are *about to do* — that terminates execution immediately.
   The message must be a past-tense summary of what you *actually did*: files created/modified (relative paths),
   commands run, and any caveats. If you have not finished all steps, keep using tools — do not send yet.
"""

    async def _plan_and_refine(self, user_request: str, history: str, session, store) -> str:
        """Generate a plan and run the interactive refinement loop with the user."""
        from .planner import generate_panorama, refine_plan
        from . import terminal as T

        T.section("Phase 1 — Implementation Overview")
        panorama_text = await generate_panorama(user_request, self.model, history=history)

        T.section("Phase 2 — Plan Refinement")
        approved_plan = await refine_plan(user_request, panorama_text, self.model, session, store)
        
        # Save the plan to the project directory
        import os
        project_path = getattr(session, "project_path", ".") or "."
        plan_file_path = os.path.join(project_path, "plan.md")
        try:
            os.makedirs(project_path, exist_ok=True)
            with open(plan_file_path, "w", encoding="utf-8") as f:
                f.write(approved_plan)
        except Exception as e:
            T.warning(f"Não foi possível salvar plan.md no diretório do projeto: {e}")
            
        return approved_plan

    async def run(self, user_request: str, history: str, **kwargs) -> str:
        """Generate and refine a plan with the user, then run autonomously."""
        session = kwargs.get("session")
        store = kwargs.get("store")

        project_context = session.context_header() if session and hasattr(session, "context_header") else ""

        approved_plan = ""
        if session and store:
            approved_plan = await self._plan_and_refine(user_request, history, session, store)

        llm_kwargs = get_agent_llm_kwargs("orchestrator")
        max_hb_config = get_agent_max_heartbeats("orchestrator", 20)
        
        from .config import get_complexity_inference_mode, ALTERNATIVE_MODEL
        from .api_keys import ensure_api_key
        
        if approved_plan and get_complexity_inference_mode() == "double":
            from .agents import make_post_plan_evaluator
            evaluator = make_post_plan_evaluator(self.model)
            with T.spinner("Avaliando esforço do plano (Inferência Dupla)..."):
                try:
                    res = await evaluator.run(AgentInput(prompt=approved_plan))
                    import json
                    data = json.loads(res.response)
                    
                    if data.get("model") == "alternative" and self.model != ALTERNATIVE_MODEL:
                        if ensure_api_key(ALTERNATIVE_MODEL):
                            T.info(f"Plano complexo detectado. Promovendo orquestrador para {ALTERNATIVE_MODEL}...")
                            self.model = ALTERNATIVE_MODEL
                            
                    if max_hb_config == "auto":
                        steps = int(data.get("estimated_steps", 10))
                        max_hb_config = min(steps * 3 + 5, 200)
                except Exception as e:
                    T.warning(f"Falha na inferência dupla de complexidade: {e}")
                    
        if max_hb_config == "auto":
            max_hb_config = 50  # Fallback for simple mode or error
            
        max_hb = int(max_hb_config)

        # Reset progress state for this new run
        AGENT_PROGRESS.heartbeat = 0
        AGENT_PROGRESS.max_heartbeats = max_hb
        AGENT_PROGRESS.last_tool = "Initializing…"
        AGENT_PROGRESS.last_args = ""
        AGENT_PROGRESS.start_time = time.monotonic()

        project_path = getattr(session, "project_path", ".") or "."
        
        from .vcs import get_vcs_strategy
        from .config import get_git_strategy
        vcs_strategy = get_vcs_strategy(get_git_strategy(), project_path)
        vcs_strategy.setup()
        
        agent_tools = self.tools + vcs_strategy.get_tools()

        agent = MemGPTAgentBlock(
            name="orchestrator",
            system_prompt=self._build_system_prompt(approved_plan, project_context),
            model=self.model,
            tools=agent_tools,
            litellm_kwargs=llm_kwargs,
            max_heartbeats=max_hb,
            debug=get_agent_debug("orchestrator", False)
        )

        project_path = getattr(session, "project_path", ".") or "."
        checkpoint_dir = os.path.join(project_path, ".opalacoder")
        checkpoint_path = os.path.join(checkpoint_dir, "session_state.json")
        is_resume = False

        if os.path.exists(checkpoint_path):
            from rich.prompt import Confirm
            if Confirm.ask("[yellow]Sessão não finalizada detectada. Deseja retomar a execução anterior?[/yellow]", default=True):
                import json
                try:
                    with open(checkpoint_path, "r") as f:
                        state = json.load(f)
                    agent.internal_history = state.get("internal_history", [])
                    agent.recursive_summary = state.get("recursive_summary", "")
                    AGENT_PROGRESS.heartbeat = state.get("heartbeat", 0)
                    is_resume = True
                except Exception as e:
                    T.warning(f"Falha ao carregar sessão anterior: {e}")
            else:
                os.remove(checkpoint_path)

        prompt = (
            f"[CONVERSATION HISTORY]\n{history}\n[END HISTORY]\n\n"
            f"[USER TASK]:\n{user_request}\n[END USER TASK]"
        )
        if is_resume:
            prompt = "SYSTEM EVENT: O sistema foi reiniciado devido a uma interrupção. Verifique seu histórico recente e retome a execução do plano usando as ferramentas."

        result_holder: list[str] = []
        agent_holder: list = []
        error_holder: list[Exception] = []

        async def _run_agent():
            try:
                vcs_strategy.pre_run(prompt)
                out = await agent.run(AgentInput(prompt=prompt))
                result_holder.append(out.response)
                agent_holder.append(agent)
            except Exception as e:
                error_holder.append(e)

        # Start the agent as a background task so we can update the live panel
        agent_task = asyncio.create_task(_run_agent())

        last_history_len = 0
        with Live(
            _build_progress_panel(AGENT_PROGRESS, max_hb),
            console=T.console,
            refresh_per_second=4,
            transient=False,
        ) as live:
            AGENT_PROGRESS.live_context = live
            while not agent_task.done():
                if live.is_started:
                    live.update(_build_progress_panel(AGENT_PROGRESS, max_hb))
                
                # Checkpointing logic
                current_history_len = len(agent.internal_history)
                if current_history_len != last_history_len:
                    last_history_len = current_history_len
                    try:
                        os.makedirs(checkpoint_dir, exist_ok=True)
                        state = {
                            "internal_history": agent.internal_history,
                            "recursive_summary": getattr(agent, "recursive_summary", ""),
                            "heartbeat": AGENT_PROGRESS.heartbeat
                        }
                        import json
                        with open(checkpoint_path, "w") as f:
                            json.dump(state, f)
                    except Exception:
                        pass
                
                await asyncio.sleep(0.25)
            AGENT_PROGRESS.live_context = None
            
            # Final render with terminal state
            if not live.is_started:
                live.start()
            live.update(_build_progress_panel(AGENT_PROGRESS, max_hb))

        # Limpa o checkpoint se finalizou com sucesso
        if os.path.exists(checkpoint_path) and not error_holder:
            try:
                os.remove(checkpoint_path)
            except Exception:
                pass

        if error_holder:
            vcs_strategy.post_run(success=False, msg=str(error_holder[0]))
            return f"Agent execution encountered an error: {error_holder[0]}"
            
        vcs_strategy.post_run(success=True, msg="Agent completed execution.")

        raw = result_holder[0] if result_holder else ""
        if not raw.strip() and agent_holder:
            raw = _extract_fallback(agent_holder[0])
        if not raw.strip():
            raw = "(Agent completed without generating a final report.)"
        return _deduplicate_response(raw)


def _extract_fallback(agent) -> str:
    """Extract the last meaningful assistant text from the agent's internal history.

    Skips messages that are raw JSON tool-call blobs (plain-text tool calls that
    the MemGPT fallback parser intercepted) — those are internal plumbing, not
    user-facing content.
    """
    import json as _json

    history = getattr(agent, "internal_history", [])
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        # Skip messages that contain tool_calls (already handled by send_message accumulator)
        if msg.get("tool_calls"):
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        # Skip raw JSON blobs (plain-text tool-call attempts)
        if content.startswith("{"):
            try:
                _json.loads(content)
                continue  # valid JSON → internal plumbing, not a report
            except _json.JSONDecodeError:
                pass
        return content
    return ""


def _deduplicate_response(text: str) -> str:
    """Remove consecutive duplicate paragraphs from the agent response.

    The MemGPT agent sometimes calls send_message multiple times with the
    same message. This collapses them into a single occurrence while
    preserving legitimately different paragraphs.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    seen: list[str] = []
    for p in paragraphs:
        if not seen or p != seen[-1]:
            seen.append(p)
    return "\n".join(seen)
