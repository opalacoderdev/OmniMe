"""Subplan executor with retry logic and execution-mode gating."""

import sys
import io
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict
from agenticblocks.core.block import Block
from agenticblocks.core.graph import WorkflowGraph
from agenticblocks.runtime.executor import WorkflowExecutor
from agenticblocks.runtime.state import NodeResult, NodeStatus
from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorBlock, CodePlanExecutorInput, CodePlanExecutorOutput
from agenticblocks.blocks.llm.agent import AgentInput

from .agents import make_executor_block, make_aggregator
from .subplan import Subplan, topological_sort
from .config import DEFAULT_MAX_RETRIES, SENSITIVE_OPS
from . import terminal as T
from .i18n import _


@contextmanager
def _sandboxed_stdin():
    """Replace sys.stdin with an empty buffer during code execution.

    Generated code sometimes calls input() despite prompt instructions.
    This makes input() return '' immediately instead of blocking the terminal.
    """
    old = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        yield
    finally:
        sys.stdin = old


def _build_task(sp: Subplan, original_request: str, context: str, global_skills_context: str = "") -> str:
    steps_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sp.steps))
    
    return (
        f"Original request: {original_request}\n\n"
        f"Subplan {sp.id} — Phase: {sp.phase}\n"
        f"Objective: {sp.objective}\n\n"
        f"Steps to execute:\n{steps_str}\n\n"
        f"Completion criterion: {sp.completion_criterion}\n\n"
        f"Context from previous subplans:\n{context}\n\n"
        "MANDATORY INSTRUCTIONS FOR THE GENERATED CODE:\n"
        "1. Generate executable Python code that CONCRETELY performs the actions above.\n"
        "2. To create files or folders: use `pathlib.Path` or `open()`.\n"
        "3. To run shell commands:\n"
        "   You MUST use `subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)`.\n"
        "   The `stdin=subprocess.DEVNULL` is vital to prevent hanging.\n"
        "4. DO NOT just print text describing what you would do — actually EXECUTE it.\n"
        "5. DO NOT use input() or interact with the user.\n"
        "6. At the end, list the created files using `print()` to confirm.\n"
        "7. PATH AWARENESS: Each subplan runs from scratch! Read the 'Context from previous subplans' to find out where the project was created. If you need to modify files from a previous step, USE ABSOLUTE PATHS or run `os.chdir(correct_path)` before running commands/creating files.\n"
        "8. NEVER start development servers or infinite processes (e.g., `npm start`, `npm run dev`, `flask run`, `python -m http.server`). Just build/configure the project. The script must terminate execution immediately."
        f"\n{global_skills_context}"
    )


def _is_sensitive(sp: Subplan) -> bool:
    """Heuristic: a subplan is sensitive if any step hints at FS/network/user ops."""
    text = " ".join(sp.steps + [sp.objective]).lower()
    keywords = {
        "criar arquivo", "escrever arquivo", "deletar", "remover arquivo",
        "apagar arquivo", "network", "rede", "enviar", "http", "post", "socket",
        "usuário", "criar conta", "sudo", "chmod",
    }
    return any(kw in text for kw in keywords)


class SubplanExecutionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

class SubplanExecutionBlock(Block[SubplanExecutionInput, CodePlanExecutorOutput]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    subplan: Subplan
    original_request: str
    results_map: dict
    executor_block: CodePlanExecutorBlock
    mode: str
    max_retries: int
    global_skills_context: str = ""

    async def run(self, input: SubplanExecutionInput) -> CodePlanExecutorOutput:
        sp = self.subplan
        # Build context from prerequisite results
        context_parts = [
            f"Result of {pid}:\n{self.results_map[pid]}"
            for pid in sp.prerequisites
            if pid in self.results_map
        ]
        context = "\n\n".join(context_parts) or "No previous context."
        task = _build_task(sp, self.original_request, context, self.global_skills_context)

        last_error: str = ""
        result = None
        success = False

        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                task += f"\n\n[SYSTEM] Previous attempt failed: {last_error}\nTry an alternative approach."
            import asyncio
            try:
                with _sandboxed_stdin():
                    # Adiciona um timeout global para evitar que scripts como 'npm start' travem o sistema
                    result = await asyncio.wait_for(
                        self.executor_block.run(CodePlanExecutorInput(task=task)),
                        timeout=180.0
                    )

                stdout = (result.execution_stdout or "").strip()
                stderr = (result.execution_stderr or "").strip()
                
                # Trunca a saída para não estourar o contexto das próximas LLMs
                if len(stdout) > 2000:
                    stdout = stdout[:1000] + "\n... [STDOUT TRUNCADO] ...\n" + stdout[-1000:]
                if len(stderr) > 2000:
                    stderr = stderr[:1000] + "\n... [STDERR TRUNCADO] ...\n" + stderr[-1000:]
                    
                output = stdout
                if stderr:
                    output += f"\n[stderr]: {stderr}"

                if result.success:
                    self.results_map[sp.id] = output or "(sem saída)"
                    success = True
                    break
                else:
                    last_error = stderr or stdout or "unknown failure"

            except asyncio.TimeoutError:
                last_error = "Timeout: The script took more than 3 minutes. Did you start a server (npm start/dev) or infinite loop? Never start servers."
                success = False
            except Exception as exc:
                last_error = str(exc)

        if not success:
            msg = f"[FAILED after {self.max_retries} attempts] {last_error}"
            self.results_map[sp.id] = msg
            if result is None:
                # Mock a failure result to maintain type
                result = CodePlanExecutorOutput(
                    success=False,
                    code_generated="",
                    execution_stdout="",
                    execution_stderr=last_error
                )
            raise RuntimeError(msg)

        return result


async def execute_subplans(
    subplans: list[Subplan],
    original_request: str,
    model: str,
    mode: str = "plan",
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, str]:
    """
    Execute each subplan leveraging AgenticBlocks WorkflowGraph for parallel execution.
    """
    from .skills import get_relevant_skills_llm
    global_skills_context = await get_relevant_skills_llm(model, original_request)

    executor_block = make_executor_block(model)
    results: dict[str, str] = {}
    errors: list[tuple[str, str]] = []

    graph = WorkflowGraph()

    # Adiciona os blocos
    for sp in subplans:
        # Confirm sensitive ops in edit mode
        if mode == "edit" and _is_sensitive(sp):
            T.warning(_("sensitive_op", id=sp.id, obj=sp.objective))
            if not T.confirm(_("execute_subplan", id=sp.id)):
                results[sp.id] = _("skipped_by_user")
                continue

        block = SubplanExecutionBlock(
            name=sp.id,
            subplan=sp,
            original_request=original_request,
            results_map=results,
            executor_block=executor_block,
            mode=mode,
            max_retries=max_retries,
            global_skills_context=global_skills_context
        )
        graph.add_block(block)

    # Adiciona dependências
    for sp in subplans:
        if sp.id not in graph.graph.nodes:
            continue
        for req in sp.prerequisites:
            if req in graph.graph.nodes:
                graph.connect(req, sp.id)

    T.section(_("executing_subplans"))

    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}[/cyan]"),
        TimeElapsedColumn(),
        console=T.console,
        transient=False,
    ) as progress:
        ui_tasks = {}

        def on_node_start(node_id: str) -> None:
            if mode != "auto":
                sp_obj = next((s for s in subplans if s.id == node_id), None)
                desc = sp_obj.objective[:50] if sp_obj else ""
                t_id = progress.add_task(f"[{node_id}] {desc}...", total=None)
                ui_tasks[node_id] = t_id

        def on_node_end(result: NodeResult) -> None:
            if mode != "auto":
                t_id = ui_tasks.get(result.node_id)
                if t_id is not None:
                    # Remove do progress bar e imprime o resultado na tela final
                    progress.remove_task(t_id)
                    
                if result.status == NodeStatus.DONE:
                    T.console.print(f"  [bold green]✓[/bold green] {result.node_id} {_('completed')} ({result.duration_ms/1000:.1f}s)")
                else:
                    T.console.print(f"  [bold red]✗[/bold red] {result.node_id} {_('failed')} ({result.duration_ms/1000:.1f}s)")
                    if result.error:
                        errors.append((result.node_id, str(result.error)))

        workflow = WorkflowExecutor(
            graph,
            on_node_start=on_node_start,
            on_node_end=on_node_end,
            verbose=False
        )

        await workflow.run()

    if errors:
        T.show_error_report(errors)

    return results


async def aggregate_results(
    results: dict[str, str],
    original_request: str,
    model: str,
) -> str:
    T.thinking(_("aggregating_results"))
    summary = "\n\n".join(
        f"=== {sp_id} ===\n{output}" for sp_id, output in results.items()
    )
    prompt = (
        f"ORIGINAL REQUEST: {original_request}\n\n"
        f"SUBPLAN RESULTS:\n{summary}"
    )
    with T.spinner(_("synthesizing_final_result")):
        aggregator = make_aggregator(model)
        agg = await aggregator.run(AgentInput(prompt=prompt))
    return agg.response

