"""MemGPT-style autonomous orchestrator with real-time live progress panel."""

import asyncio
import time
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box

import abc

from agenticblocks.blocks.llm.memgpt_agent import MemGPTAgentBlock
from agenticblocks.blocks.llm.agent import AgentInput
from .tools import get_available_tools, AGENT_PROGRESS
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
        "read_file": "blue",
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
    def __init__(self, model: str):
        super().__init__(model)
        self.tools = get_available_tools()

    def _build_system_prompt(self, approved_plan: str = "", project_context: str = "") -> str:
        plan_section = ""
        if approved_plan:
            plan_section = f"""
## APPROVED PLAN
The user has reviewed and approved the following plan. Follow it faithfully:

{approved_plan}

"""
        project_section = ""
        if project_context:
            # Extract path from context_header format "[PROJECT: name | PATH: /some/path]"
            import re as _re
            _m = _re.search(r"PATH:\s*(.+?)\]", project_context)
            proj_path = _m.group(1).strip() if _m else "(see context)"
            project_section = f"""
## WORKSPACE
{project_context.strip()}
- ALL files you create or modify MUST be placed inside: `{proj_path}`
- Use absolute paths when calling write_file and run_command, rooted at `{proj_path}`.
- Never write files outside this directory unless explicitly requested.
"""
        return f"""You are the ABCode Autonomous Orchestrator — an expert software engineer agent.
{project_section}
You operate in a continuous loop and have access to the filesystem and terminal.
{plan_section}
## YOUR MISSION
Solve coding tasks autonomously. This includes: creating NEW projects AND fixing/updating EXISTING projects
when the user reports bugs, errors, or problems with previously generated code.

## RULES
1. **ACT, don't ask**: Create directories, write files, run `npm install`, `pip install`, or any standard
   dev command WITHOUT asking for permission. Just do it.
2. **Use ask_human ONLY** for genuinely dangerous or irreversible actions: `rm -rf`, `sudo`, accessing
   credentials, or modifying files outside the project workspace.
3. **Fix bugs autonomously**: If the user reports a bug or error in existing code:
   a. First use `read_file` to read the relevant files.
   b. Identify the problem from the user's description.
   c. Use `write_file` to fix the files in place. Do NOT recreate from scratch unless necessary.
   d. Report exactly what you changed and why.
4. **Never start servers**: Do NOT run `npm start`, `npm run dev`, `flask run`, or any long-running process.
5. **Verify your work**: After writing code, run a quick syntax check (e.g. `node --check file.js`).
6. **Report ONCE**: Call `send_message` exactly ONCE at the end with a concise summary of what was done.
   Do NOT repeat the same message multiple times.
"""

    async def _plan_and_refine(self, user_request: str, history: str, session, store) -> str:
        """Generate a plan and run the interactive refinement loop with the user."""
        from .planner import generate_panorama, refine_plan
        from . import terminal as T

        T.section("Phase 1 — Implementation Overview")
        panorama_text = await generate_panorama(user_request, self.model, history=history)

        T.section("Phase 2 — Plan Refinement")
        approved_plan = await refine_plan(user_request, panorama_text, self.model, session, store)
        return approved_plan

    async def run(self, user_request: str, history: str, **kwargs) -> str:
        """Generate and refine a plan with the user, then run autonomously."""
        session = kwargs.get("session")
        store = kwargs.get("store")

        project_context = session.context_header() if session and hasattr(session, "context_header") else ""

        approved_plan = ""
        if session and store:
            approved_plan = await self._plan_and_refine(user_request, history, session, store)

        max_hb = 20

        # Reset progress state for this new run
        AGENT_PROGRESS.heartbeat = 0
        AGENT_PROGRESS.max_heartbeats = max_hb
        AGENT_PROGRESS.last_tool = "Initializing…"
        AGENT_PROGRESS.last_args = ""
        AGENT_PROGRESS.start_time = time.monotonic()

        agent = MemGPTAgentBlock(
            name="orchestrator",
            system_prompt=self._build_system_prompt(approved_plan, project_context),
            model=self.model,
            tools=self.tools,
            litellm_kwargs={"temperature": 0.2, "num_ctx": 8192},
            max_heartbeats=max_hb,
            debug=False
        )

        prompt = (
            f"[CONVERSATION HISTORY]\n{history}\n[END HISTORY]\n\n"
            f"[USER TASK]:\n{user_request}"
        )

        result_holder: list[str] = []
        error_holder: list[Exception] = []

        async def _run_agent():
            try:
                out = await agent.run(AgentInput(prompt=prompt))
                result_holder.append(out.response)
            except Exception as e:
                error_holder.append(e)

        # Start the agent as a background task so we can update the live panel
        agent_task = asyncio.create_task(_run_agent())

        with Live(
            _build_progress_panel(AGENT_PROGRESS, max_hb),
            console=T.console,
            refresh_per_second=4,
            transient=False,
        ) as live:
            while not agent_task.done():
                live.update(_build_progress_panel(AGENT_PROGRESS, max_hb))
                await asyncio.sleep(0.25)
            # Final render with terminal state
            live.update(_build_progress_panel(AGENT_PROGRESS, max_hb))

        if error_holder:
            return f"Agent execution encountered an error: {error_holder[0]}"

        raw = result_holder[0] if result_holder else "(No response from agent)"
        return _deduplicate_response(raw)


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


class DeterministicOrchestratorStrategy(BaseOrchestratorStrategy):
    """
    A deterministic DAG-based orchestrator suitable for smaller models.
    Executes a rigid pipeline: Panorama -> Refine -> Decompose -> Execute -> Aggregate.
    """
    async def run(self, user_request: str, history: str, **kwargs) -> str:
        session = kwargs.get("session")
        store = kwargs.get("store")
        max_retries = kwargs.get("max_retries", 3)
        
        if not session or not store:
            raise ValueError("Deterministic strategy requires 'session' and 'store' kwargs.")

        from .planner import generate_panorama, refine_plan, decompose_plan
        from .executor import execute_subplans, aggregate_results
        from .subplan import topological_sort
        
        request_with_history = user_request
        if history:
            request_with_history = f"[CONVERSATION HISTORY]\n{history}\n[END HISTORY]\n\n[USER TASK]:\n{user_request}"
        
        # 1. Panorama
        T.section("Fase 1 — Panorama de Implementação")
        panorama_text = await generate_panorama(user_request, self.model, history=history)
        
        # 2. Refinement
        T.section("Fase 2 — Refinamento do Plano")
        plan_text = await refine_plan(user_request, panorama_text, self.model, session, store)
        
        # 3. Decomposition
        T.section("Fase 3 — Decomposição Técnica")
        subplans = await decompose_plan(plan_text, self.model)
        if not subplans:
            return "O planejamento falhou ou foi abortado. Nenhuma tarefa gerada."
            
        subplans = topological_sort(subplans)
        
        # 4. Execution
        T.section("Fase 4 — Execução Automática")
        # Use the refined plan as the authoritative context for executors, not the raw
        # conversation history, which may contain stale results from previous sessions
        # that reference incorrect technology choices (e.g. Vite when user wanted plain HTML).
        executor_context = f"[REFINED PLAN]:\n{plan_text}\n\n[USER REQUEST]:\n{user_request}"
        results = await execute_subplans(
            subplans=subplans,
            original_request=executor_context,
            model=self.model,
            mode=session.mode,
            max_retries=max_retries,
            user_request_for_dir=user_request,
        )

        # 5. Aggregation
        T.section("Fase 5 — Resultado Final")
        # Pass the refined plan so the aggregator knows the actual tech stack chosen.
        aggregation_context = f"[REFINED PLAN]:\n{plan_text}\n\n[USER REQUEST]:\n{user_request}"
        final_response = await aggregate_results(results, aggregation_context, self.model)
        return final_response
