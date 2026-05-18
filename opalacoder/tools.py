"""Tools for the OpalaCoder Autonomous Agent (MemGPT pattern + HITL)."""

import os
import subprocess
import time
import ast
from pathlib import Path
from agenticblocks.core.function_block import as_tool
from . import terminal as T

# ─── Shared progress state ───────────────────────────────────────────────────
# The orchestrator reads these to render a live progress panel.

class _AgentProgress:
    def __init__(self):
        self.heartbeat: int = 0
        self.max_heartbeats: int = 15
        self.last_tool: str = "—"
        self.last_args: str = ""
        self.start_time: float = time.monotonic()
        self.live_context = None

    def update(self, tool_name: str, args_preview: str = "") -> None:
        self.heartbeat += 1
        self.last_tool = tool_name
        self.last_args = args_preview[:80] if args_preview else ""

    def elapsed(self) -> str:
        secs = int(time.monotonic() - self.start_time)
        m, s = divmod(secs, 60)
        return f"{m}m{s:02d}s"


AGENT_PROGRESS = _AgentProgress()

# Set once at session start via set_project_path(); all tools use this as their workspace.
_PROJECT_PATH: str = ""
_PROJECT_SESSION = None
_PROJECT_STORE = None

def set_project_context(session, store=None) -> None:
    global _PROJECT_PATH, _PROJECT_SESSION, _PROJECT_STORE
    _PROJECT_SESSION = session
    _PROJECT_STORE = store
    _PROJECT_PATH = os.path.abspath(session.project_path) if getattr(session, "project_path", "") else os.getcwd()

def get_project_path() -> str:
    return _PROJECT_PATH or os.getcwd()


def _resolve_path(path: str) -> str:
    """Make path absolute, rooted at the project directory if relative."""
    if os.path.isabs(path):
        return path
    return os.path.join(get_project_path(), path)


def _preview(value: object, max_len: int = 60) -> str:
    """Return a short, single-line preview of any argument value."""
    s = str(value).replace("\n", " ")
    return s[:max_len] + "…" if len(s) > max_len else s


# ─── Tools ───────────────────────────────────────────────────────────────────

@as_tool(name="read_file", description="Read the contents of a file in the project workspace. Relative paths are resolved from the project directory.")
def read_file(path: str) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("read_file", f"path={_preview(resolved)}")
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading {resolved}: {e}"


@as_tool(name="write_file", description="Write or overwrite a file inside the project directory. Relative paths are resolved from the project directory. Creates parent directories if needed.")
def write_file(path: str, content: str) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("write_file", f"path={_preview(resolved)}")
    try:
        Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {resolved}."
    except Exception as e:
        return f"Error writing {resolved}: {e}"


@as_tool(name="run_command", description="Execute a non-interactive shell command (e.g. ls, mkdir, grep, npm install). Runs inside the project directory. Returns stdout/stderr. NEVER run servers or infinite processes.")
def run_command(command: str) -> str:
    AGENT_PROGRESS.update("run_command", f"$ {_preview(command)}")
    cwd = get_project_path()
    try:
        res = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
            cwd=cwd,
        )
        out = res.stdout.strip()
        err = res.stderr.strip()
        # Truncate large outputs
        if len(out) > 2000:
            out = out[:1000] + "\n... [TRUNCATED] ...\n" + out[-500:]
        if len(err) > 2000:
            err = err[:1000] + "\n... [TRUNCATED] ...\n" + err[-500:]
        output = ""
        if out:
            output += f"STDOUT:\n{out}\n"
        if err:
            output += f"STDERR:\n{err}\n"
        return output if output else "Command executed successfully (no output)."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        return f"Error running command: {e}"


@as_tool(name="search_code", description="Search for a specific string across all files using grep. Searches inside the project directory by default.")
def search_code(query: str, path: str = ".") -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("search_code", f"query={_preview(query)} path={_preview(resolved)}")
    try:
        res = subprocess.run(
            f"grep -rn '{query}' {resolved}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=get_project_path(),
        )
        return res.stdout if res.stdout else "No matches."
    except Exception as e:
        return f"Error searching code: {e}"


@as_tool(
    name="ask_human",
    description=(
        "Pause execution and ask the human a critical question. "
        "Use ONLY for genuinely dangerous or irreversible operations such as: "
        "running 'rm -rf', 'sudo' commands, accessing credentials, or modifying files outside the workspace. "
        "NEVER use for: creating directories, creating files, writing code, installing common packages (npm, pip), "
        "or any standard development task. Just do those things directly."
    )
)
def ask_human(question: str) -> str:
    AGENT_PROGRESS.update("ask_human", _preview(question))
    
    if getattr(AGENT_PROGRESS, "live_context", None):
        AGENT_PROGRESS.live_context.stop()
        
    try:
        T.warning(f"\n[Agent requires input]: {question}")
        return T.ask("Your response")
    finally:
        if getattr(AGENT_PROGRESS, "live_context", None):
            AGENT_PROGRESS.live_context.start()


@as_tool(
    name="get_project_overview",
    description=(
        "Return a compact overview of the current project: directory tree (max depth 3), "
        "file count by type, and a summary of key files (README, package.json, requirements.txt, etc.). "
        "Call this at the start of any task to understand the project before acting."
    ),
)
def get_project_overview() -> str:
    AGENT_PROGRESS.update("get_project_overview")
    root = Path(get_project_path())

    if not root.exists():
        return f"Project directory does not exist yet: {root}"

    # ── Directory tree (depth ≤ 3, skip hidden & node_modules/__pycache__) ──
    SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", "dist", "build"}

    def _tree(path: Path, prefix: str = "", depth: int = 0) -> list[str]:
        if depth > 3:
            return ["    " * depth + "…"]
        lines = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return []
        for entry in entries:
            if entry.name.startswith(".") or entry.name in SKIP:
                continue
            connector = "├── " if entry != entries[-1] else "└── "
            lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
            if entry.is_dir():
                extension = "│   " if entry != entries[-1] else "    "
                lines.extend(_tree(entry, prefix + extension, depth + 1))
        return lines

    tree_lines = _tree(root)
    tree_str = f"{root.name}/\n" + "\n".join(tree_lines) if tree_lines else f"{root.name}/  (empty)"

    # ── File count by extension ──
    ext_count: dict[str, int] = {}
    total = 0
    for p in root.rglob("*"):
        if p.is_file() and not any(part in SKIP or part.startswith(".") for part in p.parts):
            ext = p.suffix.lower() or "(no ext)"
            ext_count[ext] = ext_count.get(ext, 0) + 1
            total += 1
    ext_summary = ", ".join(
        f"{ext}: {n}" for ext, n in sorted(ext_count.items(), key=lambda x: -x[1])[:8]
    )

    # ── Key file snapshots ──
    KEY_FILES = ["README.md", "package.json", "requirements.txt", "pyproject.toml",
                 "Makefile", "Dockerfile", "docker-compose.yml", ".env.example"]
    snippets = []
    for name in KEY_FILES:
        kf = root / name
        if kf.exists():
            try:
                content = kf.read_text(encoding="utf-8", errors="replace")[:400]
                snippets.append(f"### {name}\n{content.strip()}")
            except Exception:
                pass

    parts = [
        f"## Project: {root.name}",
        f"Path: {root}",
        f"Total files: {total}  |  By type: {ext_summary or 'n/a'}",
        "",
        "## Directory structure",
        tree_str,
    ]
    if snippets:
        parts += ["", "## Key files"] + snippets

    return "\n".join(parts)


@as_tool(
    name="get_file_overview",
    description=(
        "Return an overview of a file's structure. For Python files, it lists classes, functions, "
        "and methods with their start and end line numbers. For other files, it returns the first 100 lines."
    )
)
def get_file_overview(path: str) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("get_file_overview", f"path={_preview(resolved)}")
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
            
        if not path.endswith(".py"):
            lines = content.splitlines()
            preview = "\n".join(lines[:100])
            return f"Overview for {path} (non-Python):\n{preview}" + ("\n... [TRUNCATED]" if len(lines) > 100 else "")

        tree = ast.parse(content)
        overview = [f"File: {path}"]
        
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = node.lineno
                end = node.end_lineno
                overview.append(f"{node.__class__.__name__} '{node.name}' (lines {start}-{end})")
                
                if isinstance(node, ast.ClassDef):
                    for subnode in node.body:
                        if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            sub_start = subnode.lineno
                            sub_end = subnode.end_lineno
                            overview.append(f"  Method '{subnode.name}' (lines {sub_start}-{sub_end})")
        
        if len(overview) == 1:
            overview.append("No classes or functions found.")
            
        return "\n".join(overview)
    except Exception as e:
        return f"Error generating overview for {resolved}: {e}"

@as_tool(
    name="write_content_pos",
    description=(
        "Insert content into a file starting at a specific line number (1-indexed). "
        "The new content will be inserted just before the specified line."
    )
)
def write_content_pos(path: str, content: str, pos: int) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("write_content_pos", f"path={_preview(resolved)} pos={pos}")
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        idx = max(0, min(pos - 1, len(lines)))
        
        if content and not content.endswith('\n'):
            content += '\n'
            
        lines.insert(idx, content)
        
        with open(resolved, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
        return f"Successfully inserted content at line {pos} in {resolved}."
    except FileNotFoundError:
        return f"Error: File {resolved} not found."
    except Exception as e:
        return f"Error writing to {resolved}: {e}"

@as_tool(
    name="read_content_pos",
    description=(
        "Read a specific range of lines from a file. "
        "start_pos and end_pos are 1-indexed line numbers (inclusive)."
    )
)
def read_content_pos(path: str, start_pos: int, end_pos: int) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("read_content_pos", f"path={_preview(resolved)} lines={start_pos}-{end_pos}")
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        start_idx = max(0, start_pos - 1)
        end_idx = min(len(lines), end_pos)
        
        if start_idx >= len(lines):
            return f"Error: start_pos {start_pos} is beyond the end of the file (total lines: {len(lines)})."
            
        selected_lines = lines[start_idx:end_idx]
        return "".join(selected_lines)
    except FileNotFoundError:
        return f"Error: File {resolved} not found."
    except Exception as e:
        return f"Error reading {resolved}: {e}"

def get_available_tools():
    return [
        get_project_overview,
        get_file_overview,
        read_file,
        read_content_pos,
        write_file,
        write_content_pos,
        run_command,
        search_code,
        ask_human,
        read_core_memory,
        append_core_memory,
        search_conversation_history,
    ]

# ─── Long-Term Memory (MemGPT-style) ──────────────────────────────────────────

@as_tool(name="read_core_memory", description="Read the global 'Core Memory' of the project. Contains rules, persistent context, and architectural decisions you should follow.")
def read_core_memory() -> str:
    AGENT_PROGRESS.update("read_core_memory")
    if not _PROJECT_SESSION:
        return "Core memory not available (no active session)."
    return getattr(_PROJECT_SESSION, "core_memory", "") or "(Core memory is empty)"

@as_tool(name="append_core_memory", description="Append a new persistent rule, context, or decision to the Core Memory. Do this when you learn something about the user's preferences or the project's state that you want to remember across different executions.")
def append_core_memory(content: str) -> str:
    AGENT_PROGRESS.update("append_core_memory", f"content={_preview(content)}")
    if not _PROJECT_SESSION or not _PROJECT_STORE:
        return "Core memory not available (no active session)."
    
    current = getattr(_PROJECT_SESSION, "core_memory", "")
    new_mem = current + ("\n" if current else "") + "- " + content
    _PROJECT_SESSION.core_memory = new_mem
    try:
        _PROJECT_STORE.save(_PROJECT_SESSION)
        return "Successfully appended to Core Memory."
    except Exception as e:
        return f"Error saving Core Memory: {e}"

@as_tool(name="search_conversation_history", description="Search through the past conversations of this project using semantic search (RAG) to remember previous context, decisions, or user instructions. Use this when you need context about past tasks.")
def search_conversation_history(query: str, limit: int = 5) -> str:
    AGENT_PROGRESS.update("search_conversation_history", f"query={_preview(query)}")
    if not _PROJECT_SESSION:
        return "Archival search not available (no active session)."
    
    try:
        from .archival import search_archival
        results = search_archival(_PROJECT_SESSION.name, query, limit=limit)
        if not results:
            return f"No results found in archival memory for query: '{query}'"
            
        out = [f"Found {len(results)} results in Archival Memory:"]
        for r in results:
            out.append(f"[{r['timestamp']} | {r['role'].upper()}] {r['content']}")
        return "\n".join(out)
    except Exception as e:
        return f"Error searching Archival Memory: {e}"
