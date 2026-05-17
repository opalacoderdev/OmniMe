"""Subplan executor with retry logic and execution-mode gating."""

import re
import sys
import io
from contextlib import contextmanager

from typing import Any
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


_MAX_CONTEXT_CHARS = 500


def _build_task(sp: Subplan, original_request: str, context: str, global_skills_context: str = "", cwd: str = "", project_dir: str = ".") -> str:
    steps_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sp.steps))
    # Trim shared context to avoid overflowing small model context windows
    if len(context) > _MAX_CONTEXT_CHARS:
        context = context[-_MAX_CONTEXT_CHARS:]

    return (
        f"Original request: {original_request}\n\n"
        f"Subplan {sp.id} — Phase: {sp.phase}\n"
        f"Objective: {sp.objective}\n\n"
        f"Steps to execute:\n{steps_str}\n\n"
        f"Completion criterion: {sp.completion_criterion}\n\n"
        f"--- CURRENT FILESYSTEM STATE ---\n"
        f"Your current working directory (where this script runs): {cwd}\n"
        f"Target Project Directory (where you must put your files): {project_dir}\n"
        f"--------------------------------\n\n"
        f"Context from previous subplans:\n{context}\n\n"
        "MANDATORY INSTRUCTIONS FOR THE GENERATED CODE:\n"
        "1. Generate EXECUTABLE PYTHON CODE ONLY. Do NOT output raw bash commands outside of Python strings. The entire output must be valid Python 3 syntax.\n"
        "2. To create files or folders: use `pathlib.Path` or `os.makedirs`.\n"
        "3. To run shell commands (like npm, npx, mkdir, etc): You MUST wrap them in `subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)`. DO NOT output the shell command directly.\n"
        "4. DO NOT just print text describing what you would do — actually EXECUTE it in Python.\n"
        "5. DO NOT use input() or interact with the user.\n"
        "6. At the end, list the created files using `print()` to confirm.\n"
        f"7. PATH COORDINATION: Your script runs with its working directory already set to the project root `{cwd}`. "
        "Write ALL files using paths relative to the current directory — e.g., `Path('index.html')`, `Path('src/app.js')`. "
        "NEVER use `os.chdir()`. NEVER use an absolute path. "
        "NEVER create a new project sub-folder (e.g. `html_calc/`, `calculadora-app/`, etc.) — all files MUST be placed directly in the existing structure shown in CURRENT FILESYSTEM STATE. "
        "If files already exist (listed above), MODIFY them in-place rather than creating a parallel folder.\n"
        "8. ENVIRONMENT WARNING: Your code is executed via `exec()`. Variables like `__file__` DO NOT EXIST and will cause errors. Use `os.getcwd()` instead.\n"
        "9. NEVER start any server or long-running process: this includes `npm start`, `npm run dev`, `flask run`, `python -m http.server`, `http-server`, `serve`, `uvicorn`, `gunicorn`, or any equivalent. The script MUST terminate immediately after writing files.\n"
        "10. If you use `subprocess.run`, always pass `timeout=30` to prevent blocking."
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


def _extract_context_regex(current_state: str, output: str, sp_id: str) -> str | None:
    """Extract PROJECT_DIR and created files from stdout via regex, without an LLM call.

    Returns the updated state string when the output contains enough structured
    information, or None to signal that the LLM extractor should be used instead.
    """
    from pathlib import PurePosixPath

    def _normalize_dir(path: str) -> str:
        path = path.strip()
        path = path.rstrip("/\\")
        return path or "."

    def _infer_project_dir(paths: list[str]) -> str | None:
        directories: list[str] = []
        for path in paths:
            if "/" in path:
                directories.append(PurePosixPath(path).parts[0])
            elif not PurePosixPath(path).suffix:
                directories.append(path)

        directories = [d for d in directories if d]
        if not directories:
            return None

        first = directories[0]
        if all(d == first for d in directories):
            return first
        return first

    # Detect an explicit PROJECT_DIR declaration in the output
    dir_match = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', output)
    if dir_match:
        project_dir = _normalize_dir(dir_match.group(1))
    else:
        # Try to infer from explicit folder creation patterns first
        dir_match = re.search(r'(?:Created|Writing|Wrote|Updated|Modified)\s+([^\s]+/?)', output)
        project_dir = None
        if dir_match:
            candidate = dir_match.group(1).strip()
            if candidate.endswith("/") or not PurePosixPath(candidate).suffix:
                project_dir = _normalize_dir(candidate)

        if project_dir is None:
            # Try to infer from file paths mentioned in output
            file_paths = re.findall(r'(?:Created|Writing|Wrote|Updated|Modified)\s+([^\s]+)', output)
            inferred = _infer_project_dir(file_paths)
            if inferred:
                project_dir = _normalize_dir(inferred)
            elif file_paths:
                # Root-level filenames: preserve existing PROJECT_DIR rather than
                # overwriting with "." (Bug 3 fix — avoids clobbering a valid dir).
                existing = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', current_state)
                project_dir = _normalize_dir(existing.group(1)) if existing else "."

    if project_dir is None:
        # Preserve existing PROJECT_DIR if present in current state
        existing = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', current_state)
        project_dir = _normalize_dir(existing.group(1)) if existing else None

    if project_dir is None:
        # Cannot determine project dir — delegate to LLM
        return None

    # Collect file paths mentioned in output
    files = re.findall(r'(?:Created|Writing|Wrote|Updated|Modified)\s+([^\s]+\.\w+)', output)
    files_line = ("Files: " + ", ".join(files)) if files else ""

    new_state = f"PROJECT_DIR: {project_dir}\nCompleted: {sp_id}"
    if files_line:
        new_state += f"\n{files_line}"
    # Carry over key implementation details from previous state
    for line in current_state.splitlines():
        if line.startswith(("uses ", "plain ", "framework:")):
            new_state += f"\n{line}"
    return new_state


def _build_context_from_filesystem(project_dir: str, completed_sp_id: str) -> str:
    """Build shared context by reading the actual filesystem state.

    This is the only reliable way to communicate project state between subplans.
    Parsing LLM stdout is too fragile (models mix prose with code, use unexpected
    phrasing, etc.).
    """
    from pathlib import Path

    base = Path(project_dir)
    files = sorted(
        str(p.relative_to(base))
        for p in base.rglob("*")
        if p.is_file()
    )
    files_str = "\n".join(f"  - {f}" for f in files) if files else "  (none yet)"
    return (
        f"PROJECT_DIR: . (you are already inside the project root)\n"
        f"Completed: {completed_sp_id}\n"
        f"Files already present in the project — DO NOT recreate these, only ADD or MODIFY:\n"
        f"{files_str}"
    )


def _slugify(text: str) -> str:
    """Convert a phrase to a lowercase-hyphenated slug suitable for a directory name."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text.strip())
    return text or "project"


def _infer_project_dir_from_request(request: str) -> str:
    """Derive a stable directory name from the user's original request.

    Uses the first noun phrase after common verbs ('criar', 'create', 'make',
    'build', 'desenvolver', 'develop') or falls back to a slug of the whole
    request truncated to 30 chars.
    """
    pattern = re.compile(
        r"(?:criar?|create|make|build|desenvolver?|develop)\s+(?:um?|a|an|o|a)?\s*(.+)",
        re.IGNORECASE,
    )
    m = pattern.search(request.strip())
    phrase = m.group(1).strip() if m else request.strip()
    # Take at most the first 4 words to keep the slug short
    words = phrase.split()[:4]
    return _slugify(" ".join(words))[:30] or "project"


class SharedContext:
    def __init__(self, value: str):
        self.value = value


class SharedResults:
    """Mutable dict wrapper that survives Pydantic field copying.

    Pydantic v2 copies plain ``dict`` values when initialising a BaseModel,
    breaking shared-state mutation across the caller and the block.  Wrapping
    the dict in a non-standard class makes Pydantic treat it as an opaque
    object (arbitrary type) and store it by reference.
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def __setitem__(self, key: str, value: str) -> None:
        self._data[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def to_dict(self) -> dict[str, str]:
        return self._data


class SubplanExecutionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

class SubplanExecutionBlock(Block[SubplanExecutionInput, CodePlanExecutorOutput]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    subplan: Subplan
    original_request: str
    results_map: SharedResults
    executor_block: Any
    mode: str
    max_retries: int
    global_skills_context: str = ""
    shared_state: SharedContext
    model: str
    canonical_project_dir: str  # absolute path; set once before execution starts

    async def run(self, input: SubplanExecutionInput) -> CodePlanExecutorOutput:
        import os
        sp = self.subplan
        context = self.shared_state.value
        original_cwd = os.getcwd()

        # Ensure the project directory exists and chdir into it so the LLM-generated
        # code can write to "." without needing to know the canonical dir name.
        os.makedirs(self.canonical_project_dir, exist_ok=True)

        task = _build_task(
            sp, self.original_request, context, self.global_skills_context,
            cwd=self.canonical_project_dir, project_dir=".",
        )

        last_error: str = ""
        result = None
        success = False

        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                task += f"\n\n[SYSTEM] Previous attempt failed: {last_error}\nTry an alternative approach."
            import asyncio
            try:
                try:
                    os.chdir(self.canonical_project_dir)
                    with _sandboxed_stdin():
                        result = await asyncio.wait_for(
                            self.executor_block.run(CodePlanExecutorInput(task=task)),
                            timeout=60.0
                        )
                finally:
                    os.chdir(original_cwd)

                if os.environ.get("ABCODE_DEBUG"):
                    T.console.print(f"\n[bold yellow]── DEBUG {sp.id} TASK PROMPT ──[/bold yellow]\n{task}\n")
                    T.console.print(f"\n[bold yellow]── DEBUG {sp.id} GENERATED CODE ──[/bold yellow]\n{result.code_generated if result else '(none)'}\n")
                    T.console.print(f"\n[bold yellow]── DEBUG {sp.id} STDOUT ──[/bold yellow]\n{result.execution_stdout if result else ''}\n")

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
                    self.shared_state.value = _build_context_from_filesystem(
                        self.canonical_project_dir, sp.id
                    )
                    break
                else:
                    last_error = stderr or stdout or "unknown failure"

            except asyncio.TimeoutError:
                last_error = "Timeout: The script took more than 60 seconds. Did you start a server (npm start/dev, python -m http.server, http-server, serve, etc.) or infinite loop? Never start servers."
                success = False
            except Exception as exc:
                last_error = str(exc)

        if not success:
            msg = f"[FAILED after {self.max_retries} attempts] {last_error}"
            self.results_map[sp.id] = msg
            if result is None:
                result = CodePlanExecutorOutput(
                    response=last_error,
                    success=False,
                    code_generated="",
                    execution_stdout="",
                    execution_stderr=last_error
                )
            # Return the failure result instead of raising so the WorkflowGraph
            # continues to run remaining subplans and on_node_end can report the error.
            return result

        return result


async def execute_subplans(
    subplans: list[Subplan],
    original_request: str,
    model: str,
    mode: str = "plan",
    max_retries: int = DEFAULT_MAX_RETRIES,
    user_request_for_dir: str = "",
) -> dict[str, str]:
    """
    Execute each subplan leveraging AgenticBlocks WorkflowGraph for parallel execution.

    ``user_request_for_dir`` should be the raw user request (without plan context
    prefixes) so that the project directory is named from the actual user intent rather
    than from any injected context headers.
    """
    from .skills import get_relevant_skills_llm

    task_summary = "\n".join([sp.objective for sp in subplans])
    global_skills_context = await get_relevant_skills_llm(model, task_summary)

    executor_block = make_executor_block(model)
    shared_results = SharedResults()
    errors: list[tuple[str, str]] = []

    import os
    dir_source = user_request_for_dir or original_request
    project_dir_name = _infer_project_dir_from_request(dir_source)
    canonical_project_dir = os.path.join(os.getcwd(), project_dir_name)
    shared_state = SharedContext(
        f"PROJECT_DIR: . (you are already inside the project root)\n"
        f"Files already present in the project — DO NOT recreate these, only ADD or MODIFY:\n"
        f"  (none yet)"
    )

    graph = WorkflowGraph()

    # Adiciona os blocos
    for sp in subplans:
        # Confirm sensitive ops in edit mode
        if mode == "edit" and _is_sensitive(sp):
            T.warning(_("sensitive_op", id=sp.id, obj=sp.objective))
            if not T.confirm(_("execute_subplan", id=sp.id)):
                shared_results[sp.id] = _("skipped_by_user")
                continue

        block = SubplanExecutionBlock(
            name=sp.id,
            subplan=sp,
            original_request=original_request,
            results_map=shared_results,
            executor_block=executor_block,
            mode=mode,
            max_retries=max_retries,
            global_skills_context=global_skills_context,
            shared_state=shared_state,
            model=model,
            canonical_project_dir=canonical_project_dir,
        )
        graph.add_block(block)

    # Adiciona dependências de forma estritamente sequencial
    for i in range(len(subplans)):
        if subplans[i].id not in graph.graph.nodes:
            continue
        if i > 0 and subplans[i-1].id in graph.graph.nodes:
            graph.connect(subplans[i-1].id, subplans[i].id)

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

    return shared_results.to_dict()


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

