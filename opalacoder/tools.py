"""Tools for the OpalaCoder Autonomous Agent (MemGPT pattern + HITL)."""

import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agenticblocks.core.function_block import as_tool

from . import terminal as T

# ─── Shared progress state ───────────────────────────────────────────────────
# The orchestrator reads these to render a live progress panel.

class _AgentProgress:
    def __init__(self):
        self.heartbeat: int = 0
        self.max_heartbeats: int = 15
        self.tasks_done: int = 0
        self.tasks_total: int = 0
        self.last_tool: str = "—"
        self.last_args: str = ""
        self.start_time: float = time.monotonic()
        self.live_context = None
        # Error / failure tracking
        self.task_failures: int = 0          # reviewer said task NOT DONE
        self.worker_errors: int = 0          # worker returned [ERROR ...]
        self.lint_errors: int = 0            # lint check failures from write/edit
        self.plan_retries: int = 0           # oracle reflection retries
        self.recent_events: list[str] = []   # last N notable events (errors, retries)

    def _push_event(self, msg: str) -> None:
        self.recent_events.append(msg)
        if len(self.recent_events) > 6:
            self.recent_events.pop(0)

    def record_lint_error(self, path: str) -> None:
        self.lint_errors += 1
        short = os.path.basename(path)
        self._push_event(f"[red]✗ lint[/red] {short}")

    def record_worker_error(self, task_id: str, snippet: str = "") -> None:
        self.worker_errors += 1
        snip = snippet[:60].replace("\n", " ") if snippet else ""
        self._push_event(f"[red]✗ worker[/red] {task_id}" + (f": {snip}" if snip else ""))

    def record_task_failure(self, task_id: str, reason: str = "") -> None:
        self.task_failures += 1
        snip = reason[:60].replace("\n", " ") if reason else ""
        self._push_event(f"[yellow]⚠ review[/yellow] {task_id}" + (f": {snip}" if snip else ""))

    def record_plan_retry(self, attempt: int) -> None:
        self.plan_retries += 1
        self._push_event(f"[yellow]⚠ plan retry[/yellow] #{attempt}")

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
    if session:
        _PROJECT_PATH = os.path.abspath(session.project_path) if getattr(session, "project_path", "") else os.getcwd()
        
        # Load project-specific .env file if it exists
        env_path = os.path.join(_PROJECT_PATH, ".env")
        if os.path.isfile(env_path):
            from dotenv import load_dotenv
            try:
                load_dotenv(dotenv_path=env_path, override=True)
            except Exception:
                pass
                
        # Also explicitly propagate api_key and api_base from session if present
        model_name = getattr(session, "model", None)
        alt_model_name = getattr(session, "alternative_model", None)
        env_vars = set()
        from .api_keys import get_env_var_for_model
        if model_name:
            v = get_env_var_for_model(model_name)
            if v:
                env_vars.add(v)
        if alt_model_name:
            v = get_env_var_for_model(alt_model_name)
            if v:
                env_vars.add(v)

        if getattr(session, "api_key", None):
            os.environ["OPENAI_API_KEY"] = session.api_key
            for v in env_vars:
                os.environ[v] = session.api_key
        else:
            # Only pop if they were not loaded from the current project's .env file
            # (which has already been processed by load_dotenv above)
            env_file_has_key = False
            if os.path.isfile(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if "OPENAI_API_KEY=" in content:
                            env_file_has_key = True
                except Exception:
                    pass
            if not env_file_has_key:
                os.environ.pop("OPENAI_API_KEY", None)

            for v in env_vars:
                env_file_has_v = False
                if os.path.isfile(env_path):
                    try:
                        with open(env_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            if f"{v}=" in content:
                                env_file_has_v = True
                    except Exception:
                        pass
                if not env_file_has_v:
                    os.environ.pop(v, None)

        if getattr(session, "api_base", None):
            os.environ["OPENAI_API_BASE"] = session.api_base
        else:
            env_file_has_base = False
            if os.path.isfile(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if "OPENAI_API_BASE=" in content:
                            env_file_has_base = True
                except Exception:
                    pass
            if not env_file_has_base:
                os.environ.pop("OPENAI_API_BASE", None)



        # Dynamically inject/register the configured context window (num_ctx) in LiteLLM's model mapping
        # so it doesn't fail with a BadRequestError (request exceeds available context window).
        try:
            import litellm
            model_name = getattr(session, "model", None)
            model_params = getattr(session, "model_params", None) or {}
            num_ctx = model_params.get("num_ctx")
            if model_name and num_ctx:
                # Direct registration for model in litellm's dynamic model database
                if model_name not in litellm.model_prices_and_context_window:
                    litellm.model_prices_and_context_window[model_name] = {
                        "max_tokens": num_ctx,
                        "max_input_tokens": num_ctx,
                        "max_output_tokens": num_ctx,
                        "context_window": num_ctx,
                    }
                else:
                    litellm.model_prices_and_context_window[model_name]["context_window"] = num_ctx
                    litellm.model_prices_and_context_window[model_name]["max_tokens"] = num_ctx
                    litellm.model_prices_and_context_window[model_name]["max_input_tokens"] = num_ctx
        except Exception:
            pass
    else:
        _PROJECT_PATH = os.getcwd()


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


def _auto_lint(resolved_path: str) -> str:
    """Run a quick syntax check and return the output, or empty string if clean."""
    ext = os.path.splitext(resolved_path)[1].lower()
    if ext == ".py":
        res = subprocess.run(
            ["python", "-m", "py_compile", resolved_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return (res.stdout + res.stderr).strip()
    if ext in {".js", ".ts", ".jsx", ".tsx"}:
        try:
            res = subprocess.run(
                ["node", "--check", resolved_path],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return (res.stdout + res.stderr).strip()
        except FileNotFoundError:
            return ""
    return ""


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
        try:
            from .code_index import CODE_INDEX
            CODE_INDEX.rebuild_file(resolved)
        except Exception:
            pass
        lint_output = _auto_lint(resolved)
        if lint_output:
            AGENT_PROGRESS.record_lint_error(resolved)
            return (
                f"Successfully wrote to {resolved}, but lint check found errors:\n"
                f"{lint_output}\n\nPlease fix the syntax errors."
            )
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


@as_tool(name="run_interactive_command", description="Run a command that requires user interaction (e.g. npm create, interactive scripts, prompts). The terminal control will be temporarily handed over to the user. Use this ONLY when a command needs human choices.")
def run_interactive_command(command: str) -> str:
    import sys
    AGENT_PROGRESS.update("interactive_cmd", f"$ {_preview(command)}")
    cwd = get_project_path()
    
    # Pause the live context if it exists to prevent UI tearing
    if getattr(AGENT_PROGRESS, "live_context", None):
        AGENT_PROGRESS.live_context.stop()
        
    try:
        T.warning(f"\n[Interactive Mode]: Giving terminal control to user for command: {command}")
        subprocess.run(
            command,
            shell=True,
            cwd=cwd,
        )
        return "Interactive command completed. The user interacted with it successfully."
    except Exception as e:
        return f"Error running interactive command: {e}"
    finally:
        # Resume live context
        if getattr(AGENT_PROGRESS, "live_context", None):
            AGENT_PROGRESS.live_context.start()


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
        # Try index-backed overview first (works for any language)
        try:
            from .code_index import CODE_INDEX
            project_root = get_project_path()
            rel = os.path.relpath(resolved, project_root)
            syms = CODE_INDEX.symbols_in_file(rel)
            if syms:
                overview = [f"File: {path}"]
                for sym in syms:
                    prefix = "  " if sym.kind == "method" else ""
                    overview.append(f"{prefix}{sym.kind} '{sym.name}' (line {sym.line})")
                return "\n".join(overview)
        except Exception:
            pass

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

# ─── Bug Detection ────────────────────────────────────────────────────────────

@dataclass
class BugReport:
    file: str
    line: Optional[int]
    column: Optional[int]
    severity: str        # "error" | "warning" | "info"
    message: str
    rule: str            # e.g. "pyflakes:F811", "ast:bare-except", "type:mypy"
    source: str          # "linter" | "ast" | "llm"

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "rule": self.rule,
            "source": self.source,
        }


def _collect_python_files(root: str, target: str) -> list[str]:
    resolved = _resolve_path(target)
    if os.path.isfile(resolved):
        return [resolved] if resolved.endswith(".py") else []
    py_files = []
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", "dist", "build", ".env", "tests", "opalacoder", "skills", "debug"}
    for dirpath, dirnames, filenames in os.walk(resolved):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(os.path.join(dirpath, fname))
    return py_files


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def _layer_linters(py_files: list[str], root: str) -> list[BugReport]:
    """Layer 1: run pyflakes (and mypy/pylint if available) on each file."""
    bugs: list[BugReport] = []
    python_exe = sys.executable

    # ── pyflakes ──
    try:
        res = subprocess.run(
            [python_exe, "-m", "pyflakes"] + py_files,
            capture_output=True, text=True, timeout=60,
        )
        output = res.stdout + res.stderr
        # pyflakes format: path:line: message
        pattern = re.compile(r"^(.+?):(\d+):\d*:?\s*(.+)$", re.MULTILINE)
        for m in pattern.finditer(output):
            fpath, lineno, msg = m.group(1), int(m.group(2)), m.group(3).strip()
            severity = "error" if any(w in msg.lower() for w in ("undefined", "import *", "redefinition")) else "warning"
            bugs.append(BugReport(
                file=_rel(fpath, root), line=lineno, column=None,
                severity=severity, message=msg, rule="pyflakes", source="linter",
            ))
    except Exception:
        pass

    # ── mypy (optional) ──
    try:
        res = subprocess.run(
            [python_exe, "-m", "mypy", "--no-error-summary", "--show-column-numbers",
             "--ignore-missing-imports"] + py_files,
            capture_output=True, text=True, timeout=90,
        )
        pattern = re.compile(r"^(.+?):(\d+):(\d+): (\w+): (.+)$", re.MULTILINE)
        for m in pattern.finditer(res.stdout + res.stderr):
            fpath, lineno, col, sev, msg = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
            if sev in ("error", "warning"):
                bugs.append(BugReport(
                    file=_rel(fpath, root), line=lineno, column=col,
                    severity=sev, message=msg, rule="mypy", source="linter",
                ))
    except Exception:
        pass

    # ── pylint (optional) ──
    try:
        res = subprocess.run(
            [python_exe, "-m", "pylint", "--output-format=json",
             "--disable=C,R", "--score=no"] + py_files,
            capture_output=True, text=True, timeout=90,
        )
        for item in json.loads(res.stdout or "[]"):
            sev_map = {"error": "error", "warning": "warning", "fatal": "error"}
            sev = sev_map.get(item.get("type", ""), "info")
            bugs.append(BugReport(
                file=_rel(item.get("path", ""), root),
                line=item.get("line"), column=item.get("column"),
                severity=sev, message=item.get("message", ""),
                rule=f"pylint:{item.get('message-id', '')}",
                source="linter",
            ))
    except Exception:
        pass

    return bugs


# AST patterns: (rule_id, severity, detector_fn) → detector returns message | None
_AST_CHECKS: list[tuple[str, str, object]] = []


def _ast_check(rule: str, severity: str):
    def decorator(fn):
        _AST_CHECKS.append((rule, severity, fn))
        return fn
    return decorator


@_ast_check("ast:bare-except", "warning")
def _check_bare_except(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.ExceptHandler) and node.type is None:
        return "Bare 'except:' silences all exceptions including KeyboardInterrupt/SystemExit."
    return None


@_ast_check("ast:mutable-default-arg", "error")
def _check_mutable_default(node: ast.AST) -> Optional[str]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    for default in node.args.defaults + node.args.kw_defaults:
        if default is None:
            continue
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            return f"Mutable default argument in '{node.name}' — use None and assign inside the function."
    return None


@_ast_check("ast:assert-in-prod", "warning")
def _check_assert(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Assert):
        return "Assert statement is removed when Python runs with -O; use explicit checks for runtime validation."
    return None


@_ast_check("ast:except-pass", "warning")
def _check_except_pass(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.ExceptHandler):
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            etype = ast.unparse(node.type) if node.type else "*"
            return f"'except {etype}: pass' silently swallows exceptions."
    return None


@_ast_check("ast:shadowed-builtin", "warning")
def _check_shadow_builtin(node: ast.AST) -> Optional[str]:
    _BUILTINS = frozenset({
        "list", "dict", "set", "tuple", "type", "input", "id", "hash",
        "min", "max", "sum", "len", "open", "print", "range", "zip", "map",
        "filter", "object", "str", "int", "float", "bool", "bytes",
    })
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if node.name in _BUILTINS:
            return f"'{node.name}' shadows the built-in with the same name."
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in _BUILTINS:
                return f"Variable '{target.id}' shadows the built-in with the same name."
    return None


@_ast_check("ast:return-in-finally", "error")
def _check_return_in_finally(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Try):
        for stmt in (node.finalbody if hasattr(node, "finalbody") else []):
            if isinstance(stmt, ast.Return):
                return "Return inside 'finally' block suppresses exceptions from try/except."
    return None


@_ast_check("ast:comparison-with-none", "warning")
def _check_none_equality(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Compare):
        for op in node.ops:
            if isinstance(op, (ast.Eq, ast.NotEq)):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Constant) and comparator.value is None:
                        op_str = "==" if isinstance(op, ast.Eq) else "!="
                        return f"Use 'is None' / 'is not None' instead of '{op_str} None'."
    return None


def _layer_ast(py_files: list[str], root: str) -> list[BugReport]:
    """Layer 2: walk each file's AST and run custom checks."""
    bugs: list[BugReport] = []
    for fpath in py_files:
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=fpath)
        except SyntaxError as e:
            bugs.append(BugReport(
                file=_rel(fpath, root), line=e.lineno, column=e.offset,
                severity="error", message=f"SyntaxError: {e.msg}",
                rule="ast:syntax-error", source="ast",
            ))
            continue
        except Exception:
            continue

        for node in ast.walk(tree):
            lineno = getattr(node, "lineno", None)
            for rule, severity, checker in _AST_CHECKS:
                msg = checker(node)
                if msg:
                    bugs.append(BugReport(
                        file=_rel(fpath, root), line=lineno, column=None,
                        severity=severity, message=msg, rule=rule, source="ast",
                    ))

    return bugs


async def _layer_llm(py_files: list[str], root: str, max_files: int = 3) -> list[BugReport]:
    """Layer 3: LLM spot-check on the most recently modified Python files."""
    bugs: list[BugReport] = []
    try:
        from .config import get_agent_config
        from agenticblocks.blocks.llm.agent import LLMAgentBlock, AgentInput
        cfg = get_agent_config("orchestrator")
        model = cfg.get("model", "")
        if not model:
            return bugs
    except Exception:
        return bugs

    _SYSTEM = (
        "You are a static analysis tool. Analyze the following Python code and return "
        "a JSON array of bugs. Each bug must be an object with keys: "
        "\"line\" (int or null), \"severity\" (\"error\"|\"warning\"), \"message\" (string), "
        "\"rule\" (string starting with 'llm:'). "
        "Focus on: logic errors, incorrect control flow, resource leaks, off-by-one errors, "
        "wrong variable usage, and type mismatches. "
        "Ignore style issues. If no bugs found, return []. "
        "Return ONLY the JSON array, no other text."
    )
    agent = LLMAgentBlock(
        name="llm_bug_scanner",
        system_prompt=_SYSTEM,
        model=model,
        max_iterations=1,
        model_kwargs={"max_tokens": 1024, "temperature": 0},
    )

    candidates = sorted(py_files, key=lambda p: os.path.getmtime(p), reverse=True)[:max_files]

    for fpath in candidates:
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")
            if len(source) > 6000:
                source = source[:6000] + "\n# ... [TRUNCATED]"

            result = await agent.run(AgentInput(prompt=f"```python\n{source}\n```"))
            raw = result.response or "[]"
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            if not m:
                continue
            items = json.loads(m.group(0))
            for item in items:
                if not isinstance(item, dict):
                    continue
                bugs.append(BugReport(
                    file=_rel(fpath, root),
                    line=item.get("line"),
                    column=None,
                    severity=item.get("severity", "warning"),
                    message=item.get("message", ""),
                    rule=item.get("rule", "llm:unknown"),
                    source="llm",
                ))
        except Exception:
            continue

    return bugs


@as_tool(
    name="search_bugs",
    description=(
        "Detect bugs in the project (or a specific file/directory) using three layers: "
        "(1) linters: pyflakes, mypy, pylint — when available; "
        "(2) AST analysis: custom checks for bare-except, mutable defaults, except-pass, "
        "shadowed builtins, return-in-finally, None comparisons; "
        "(3) LLM spot-check: the active orchestrator model reviews the most recently "
        "modified files for logic errors and type mismatches. "
        "Returns a structured list of bugs sorted by severity. "
        "Optionally restrict to a specific path (file or directory relative to project root). "
        "Set llm_check=False to skip the LLM layer (faster)."
    ),
)
async def search_bugs(path: str = ".", llm_check: bool = True) -> str:
    AGENT_PROGRESS.update("search_bugs", f"path={_preview(path)}")
    root = get_project_path()
    py_files = _collect_python_files(root, path)

    if not py_files:
        return f"No Python files found in '{path}'."

    all_bugs: list[BugReport] = []
    all_bugs.extend(_layer_linters(py_files, root))
    all_bugs.extend(_layer_ast(py_files, root))
    if llm_check:
        all_bugs.extend(await _layer_llm(py_files, root))

    if not all_bugs:
        return f"No bugs detected in {len(py_files)} Python file(s)."

    # Deduplicate by (file, line, rule, message)
    seen: set[tuple] = set()
    unique: list[BugReport] = []
    for b in all_bugs:
        key = (b.file, b.line, b.rule, b.message[:80])
        if key not in seen:
            seen.add(key)
            unique.append(b)

    # Sort: errors first, then by file and line
    sev_order = {"error": 0, "warning": 1, "info": 2}
    unique.sort(key=lambda b: (sev_order.get(b.severity, 9), b.file, b.line or 0))

    lines = [f"Found {len(unique)} bug(s) in {len(py_files)} file(s):\n"]
    for b in unique:
        loc = f"{b.file}:{b.line}" if b.line else b.file
        lines.append(f"[{b.severity.upper()}] {loc}  ({b.rule})  [{b.source}]")
        lines.append(f"  {b.message}")
    return "\n".join(lines)


def get_available_tools():
    return [
        get_project_overview,
        get_file_overview,
        read_file,
        read_content_pos,
        write_file,
        write_content_pos,
        run_command,
        run_interactive_command,
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


@as_tool(
    name="web_search",
    description=(
        "Search the web for current information, documentation, news, or any topic. "
        "Use this when you need information that may be recent, external, or not in your training data. "
        "Returns a list of results with titles, URLs and snippets. "
        "Requires web search to be enabled in OpalaCoder settings."
    ),
)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo (default) or the configured MCP server."""
    AGENT_PROGRESS.update("web_search", f"query={_preview(query)}")
    try:
        from .web_search_config import is_enabled, do_search
    except ImportError as exc:
        return f"[web_search] Configuration module unavailable: {exc}"

    if not is_enabled():
        return (
            "[web_search] Web search is currently disabled. "
            "Enable it via the Web Search toggle in the OpalaCoder chat panel."
        )

    # Bridge the async do_search into the synchronous tool interface.
    # Always use a fresh ThreadPoolExecutor so that asyncio.run() creates its own
    # event loop in a clean thread — this is safe regardless of whether the caller
    # is the main thread, an async worker thread (agenticblocks), or any other
    # context.  Using asyncio.get_event_loop() in Python 3.10+ raises RuntimeError
    # when called from a thread that never had an event loop (e.g. 'asyncio_0').
    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(__import__("asyncio").run, do_search(query, max_results))
            return future.result(timeout=30)
    except Exception as exc:
        return f"[web_search] Search failed: {exc}"
