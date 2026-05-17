"""Tools for the ABCode Autonomous Agent (MemGPT pattern + HITL)."""

import os
import subprocess
import time
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


def set_project_path(path: str) -> None:
    global _PROJECT_PATH
    _PROJECT_PATH = os.path.abspath(path)


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
    T.warning(f"\n[Agent requires input]: {question}")
    return T.ask("Your response")


def get_available_tools():
    return [
        read_file,
        write_file,
        run_command,
        search_code,
        ask_human,
    ]
