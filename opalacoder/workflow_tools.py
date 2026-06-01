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
        "To DELETE a line entirely, set new_str to an empty string and old_str to the full line content "
        "(including the newline if needed), and use the `line` parameter to target the right occurrence. "
        "If old_str appears on multiple lines, supply the optional `line` parameter (1-based) "
        "to target the specific occurrence near that line number. "
        "Prefer this over the read_file + write_file sequence — it is more reliable for small models."
    ),
)
def edit_file(path: str, old_str: str, new_str: str, line: int = 0) -> str:
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
        if line <= 0:
            return (
                f"Error: old_str matches {count} locations in {path}. "
                "Supply the `line` parameter (1-based line number) to target the right occurrence, "
                "or add more surrounding context to make old_str unique."
            )
        # Find the occurrence closest to the given line number
        lines = content.splitlines(keepends=True)
        # Build character offset for each line start
        offsets = []
        pos = 0
        for ln in lines:
            offsets.append(pos)
            pos += len(ln)

        target_offset = offsets[min(line - 1, len(offsets) - 1)]
        # Find all occurrence positions
        positions = []
        search_from = 0
        while True:
            idx = content.find(old_str, search_from)
            if idx == -1:
                break
            positions.append(idx)
            search_from = idx + 1

        # Pick the occurrence closest to target_offset
        best = min(positions, key=lambda p: abs(p - target_offset))
        new_content = content[:best] + new_str + content[best + len(old_str):]
    else:
        new_content = content.replace(old_str, new_str, 1)
    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return f"Error writing {resolved}: {e}"

    lint_output = _auto_lint(resolved)
    if lint_output:
        _fail_counts[resolved] = _fail_counts.get(resolved, 0) + 1
        AGENT_PROGRESS.record_lint_error(resolved)
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
    name="replace_lines",
    description=(
        "Replace a specific range of lines in a file with new content, followed by an automatic syntax/lint check. "
        "Provide the 1-based start_line and end_line, and the new_str to replace them with. "
        "Use this instead of edit_file when you want to be precise or if edit_file fails with old_str not found."
    ),
)
def replace_lines(path: str, start_line: int, end_line: int, new_str: str) -> str:
    resolved = _resolve_path(path)
    AGENT_PROGRESS.update("replace_lines", f"path={_preview(resolved)} lines={start_line}-{end_line}")

    if start_line <= 0 or end_line < start_line:
        return "Error: Invalid line range. start_line must be > 0 and end_line >= start_line."

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.read().splitlines(keepends=True)
    except FileNotFoundError:
        return f"Error: file not found: {resolved}"
    except Exception as e:
        return f"Error reading {resolved}: {e}"

    if start_line > len(lines):
        return f"Error: start_line ({start_line}) is beyond the end of the file ({len(lines)} lines)."

    # Replace lines [start_line-1 : end_line]
    # new_str might not have a trailing newline, so we add one if the original block had it.
    prefix = lines[:start_line - 1]
    suffix = lines[end_line:]
    
    new_content = "".join(prefix) + new_str
    if new_str and not new_str.endswith("\n"):
        new_content += "\n"
    new_content += "".join(suffix)

    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return f"Error writing {resolved}: {e}"

    lint_output = _auto_lint(resolved)
    if lint_output:
        _fail_counts[resolved] = _fail_counts.get(resolved, 0) + 1
        AGENT_PROGRESS.record_lint_error(resolved)
        msg = f"Edit applied but lint check failed:\n{lint_output}"
        if _fail_counts[resolved] >= 2:
            msg += _DECOMPOSE_HINT
        return msg

    _fail_counts[resolved] = 0
    try:
        CODE_INDEX.rebuild_file(resolved)
    except Exception:
        pass
    return f"Lines {start_line}-{end_line} replaced successfully in {path}. Lint check passed."


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


def get_workflow_tools(skill_tools: list = None) -> list:
    """Return the minimal tool set for workers plus skill tools when active.

    Intentionally small — large tool lists confuse small models.
    Workers execute atomic commands; they read, edit, write, run, and signal done.
    """
    from .tools import write_file, run_command, search_code, read_content_pos
    base = [
        read_file,        # token-aware read (workflow_tools version)
        read_content_pos, # read specific line range of large files
        write_file,       # create new files or full rewrites
        edit_file,        # find-replace + auto-lint (primary edit tool)
        replace_lines,    # line-range replace when edit_file old_str fails
        run_command,      # lint, compile, node --check
        search_code,      # grep across project when worker needs to locate something
        send_message,     # signals task completion (termination tool)
    ]
    if skill_tools:
        base_names = {getattr(t, "name", None) or getattr(t, "__name__", None) for t in base}
        for st in skill_tools:
            st_name = getattr(st, "name", None) or getattr(st, "__name__", None)
            if st_name not in base_names:
                base.append(st)
                base_names.add(st_name)
    return base
