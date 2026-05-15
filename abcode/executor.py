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
        f"Pedido original: {original_request}\n\n"
        f"Subplano {sp.id} — Fase: {sp.phase}\n"
        f"Objetivo: {sp.objective}\n\n"
        f"Passos a executar:\n{steps_str}\n\n"
        f"Critério de conclusão: {sp.completion_criterion}\n\n"
        f"Contexto de subplanos anteriores:\n{context}\n\n"
        "INSTRUÇÕES OBRIGATÓRIAS PARA O CÓDIGO GERADO:\n"
        "1. Gere código Python executável que realize CONCRETAMENTE as ações acima.\n"
        "2. Para criar arquivos ou pastas: use `pathlib.Path` ou `open()`.\n"
        "3. Para rodar comandos shell:\n"
        "   Use OBRIGATORIAMENTE `subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)`.\n"
        "   O `stdin=subprocess.DEVNULL` é vital para evitar travamentos.\n"
        "4. NÃO apenas imprima texto descrevendo o que faria — EXECUTE de verdade.\n"
        "5. NÃO use input() nem interação com o usuário.\n"
        "6. Ao final, liste os arquivos criados com `print()` para confirmar.\n"
        "7. ATENÇÃO AOS CAMINHOS: Cada subplano roda do zero! Leia o 'Contexto de subplanos anteriores' para descobrir onde o projeto foi criado. Se precisar modificar arquivos do passo anterior, USE CAMINHOS ABSOLUTOS ou faça `os.chdir(caminho_correto)` antes de rodar os comandos/criar arquivos."
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
            f"Resultado de {pid}:\n{self.results_map[pid]}"
            for pid in sp.prerequisites
            if pid in self.results_map
        ]
        context = "\n\n".join(context_parts) or "Nenhum contexto anterior."
        task = _build_task(sp, self.original_request, context, self.global_skills_context)

        last_error: str = ""
        result = None
        success = False

        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                task += f"\n\n[SISTEMA] Tentativa anterior falhou: {last_error}\nTente uma abordagem alternativa."
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
                    last_error = stderr or stdout or "falha desconhecida"

            except asyncio.TimeoutError:
                last_error = "Timeout: O script demorou mais de 3 minutos. Você iniciou algum servidor (npm start/dev) ou loop infinito? Nunca inicie servidores."
                success = False
            except Exception as exc:
                last_error = str(exc)

        if not success:
            msg = f"[FALHOU após {self.max_retries} tentativas] {last_error}"
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
            T.warning(f"{sp.id} contém operação sensível: {sp.objective}")
            if not T.confirm(f"Executar {sp.id}?"):
                results[sp.id] = "[PULADO pelo usuário]"
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

    T.section("Executando Subplanos (AgenticBlocks WorkflowGraph)")

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
                    T.console.print(f"  [bold green]✓[/bold green] {result.node_id} concluído ({result.duration_ms/1000:.1f}s)")
                else:
                    T.console.print(f"  [bold red]✗[/bold red] {result.node_id} falhou ({result.duration_ms/1000:.1f}s)")
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
    T.thinking("Agregando resultados…")
    summary = "\n\n".join(
        f"=== {sp_id} ===\n{output}" for sp_id, output in results.items()
    )
    prompt = (
        f"PEDIDO ORIGINAL: {original_request}\n\n"
        f"RESULTADOS DOS SUBPLANOS:\n{summary}"
    )
    with T.spinner("Sintetizando resultado final…"):
        aggregator = make_aggregator(model)
        agg = await aggregator.run(AgentInput(prompt=prompt))
    return agg.response

