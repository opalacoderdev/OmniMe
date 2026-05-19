"""Composite and smart tools for WorkflowOrchestratorStrategy (specs3.md)."""

import glob
import os
import subprocess
from pathlib import Path

from agenticblocks.core.function_block import as_tool

from .code_index import CODE_INDEX
from .tools import AGENT_PROGRESS, _auto_lint, _preview, _resolve_path, get_file_overview, get_project_path

# Failure counter per file path (specs3 decompose-on-failure)
_fail_counts: dict[str, int] = {}

_DECOMPOSE_HINT = (
    "\n\n[Hint — decompose]: You have failed here twice. "
    "Identify the single line that is wrong and fix only that."
)




@as_tool(
    name="edit_file",
    description=(
        "Atomic find-replace inside a file, followed by an automatic syntax/lint check. "
        "Provide the exact text to replace (old_str) and its replacement (new_str). "
        "old_str must appear exactly once in the file. "
        "Prefer this over the read_file + write_file sequence — it is more reliable for small models."
    ),
)
def edit_file(path: str, old_str: str, new_str: str) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("edit_file", f"path={_preview(resolved)}")

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: file not found: {resolved}"
    except Exception as e:
        return f"Error reading {resolved}: {e}"

    count = content.count(old_str)
    if count == 0:
        return f"Error: old_str not found in {path}. Double-check the exact text to replace."
    if count > 1:
        return (
            f"Error: old_str matches {count} locations in {path}. "
            "Add more surrounding context to make it unique."
        )

    new_content = content.replace(old_str, new_str, 1)
    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return f"Error writing {resolved}: {e}"

    lint_output = _auto_lint(resolved)
    if lint_output:
        _fail_counts[resolved] = _fail_counts.get(resolved, 0) + 1
        msg = f"Edit applied but lint check failed:\n{lint_output}"
        if _fail_counts[resolved] >= 2:
            msg += _DECOMPOSE_HINT
        return msg

    _fail_counts[resolved] = 0
    try:
        CODE_INDEX.rebuild_file(resolved)
    except Exception:
        pass
    return f"Edit applied successfully to {path}. Lint check passed."


@as_tool(
    name="find_symbol",
    description=(
        "Find a function, class, or method by name across the entire project (all languages) "
        "and return its definition plus the functions it calls (one level of call graph). "
        "Uses the persistent code index — much faster than grep. "
        "Use instead of search_code when you need to understand how something is implemented."
    ),
)
def find_symbol(symbol_name: str) -> str:
    AGENT_PROGRESS.update("find_symbol", f"symbol={_preview(symbol_name)}")
    project_root = get_project_path()

    symbols = CODE_INDEX.search(symbol_name, limit=10)

    if symbols:
        blocks: list[str] = []
        for sym in symbols:
            abs_path = os.path.join(project_root, sym.file)
            snippet = ""
            try:
                lines = Path(abs_path).read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(0, sym.line - 1)
                # Read up to 60 lines from the definition
                end = min(len(lines), start + 60)
                snippet = "\n".join(lines[start:end])
            except Exception:
                snippet = sym.signature

            block = (
                f"### {sym.kind} `{sym.name}` in {sym.file} (line {sym.line})\n"
                f"```\n{snippet}\n```"
            )
            if sym.calls:
                block += f"\nCalls: {', '.join(sym.calls[:20])}"
            blocks.append(block)
        return "\n\n".join(blocks)

    # Fallback: grep (index may not cover the file yet)
    try:
        res = subprocess.run(
            f"grep -rn --include='*' '{symbol_name}' {project_root}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        grep_out = res.stdout.strip()
        if grep_out:
            return f"Symbol not found in index. grep matches:\n{grep_out[:2000]}"
    except Exception:
        pass

    return f"Symbol '{symbol_name}' not found in index or via grep."


@as_tool(
    name="find_callers",
    description=(
        "Find all functions/methods that call a given symbol anywhere in the project. "
        "Use this to understand the impact of changing a function — who depends on it."
    ),
)
def find_callers(symbol_name: str) -> str:
    AGENT_PROGRESS.update("find_callers", f"symbol={_preview(symbol_name)}")

    callers = CODE_INDEX.find_callers(symbol_name, limit=20)

    if not callers:
        # Fallback: grep for call-site pattern
        project_root = get_project_path()
        try:
            res = subprocess.run(
                f"grep -rn '{symbol_name}(' {project_root}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            grep_out = res.stdout.strip()
            if grep_out:
                return f"No callers in index. grep call-site matches:\n{grep_out[:2000]}"
        except Exception:
            pass
        return f"No callers found for '{symbol_name}'."

    lines: list[str] = [f"Callers of `{symbol_name}` ({len(callers)} found):"]
    for sym in callers:
        lines.append(f"  • {sym.kind} `{sym.name}` in {sym.file}:{sym.line}  [{sym.signature[:80]}]")
    return "\n".join(lines)


@as_tool(
    name="read_file",
    description=(
        "Token-aware file reader. Returns the full file for small files (<= max_lines). "
        "For large files, returns an AST overview plus anchor lines and instructs you to use "
        "read_content_pos(path, start, end) to read the relevant section. "
        "Use this instead of write_file when opening a file for the first time."
    ),
)
def read_file(path: str, max_lines: int = 150) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("read_file", f"path={_preview(resolved)}")

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: file not found: {resolved}"
    except Exception as e:
        return f"Error reading {resolved}: {e}"

    lines = content.splitlines()
    n = len(lines)

    if n <= max_lines:
        return content

    # Large file: return overview + anchor lines
    overview = get_file_overview(path)
    anchor_top = "\n".join(lines[:30])
    anchor_bottom = "\n".join(lines[-10:])

    return (
        f"{overview}\n\n"
        f"--- First 30 lines ---\n{anchor_top}\n\n"
        f"--- Last 10 lines ---\n{anchor_bottom}\n\n"
        f"File is large ({n} lines). "
        f"Use read_content_pos('{path}', start, end) to read a specific section."
    )


@as_tool(
    name="send_message",
    description=(
        "Signal that the task is complete and provide a past-tense summary of what was done. "
        "Call this ONCE after all files have been written and verified. "
        "Do NOT call it to describe what you are about to do — only after finishing."
    ),
)
def send_message(message: str) -> str:
    AGENT_PROGRESS.update("send_message", _preview(message))
    return f"[DONE] {message}"


def get_workflow_tools() -> list:
    """Return all base tools plus workflow-specific composite/smart tools."""
    from .tools import get_available_tools
    return get_available_tools() + [edit_file, find_symbol, find_callers, read_file, send_message]
