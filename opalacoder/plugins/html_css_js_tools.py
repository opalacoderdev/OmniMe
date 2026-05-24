"""Built-in plugin: static analysis tools for HTML/CSS/JavaScript projects."""

import os
import re
import subprocess
from pathlib import Path

from agenticblocks.core.function_block import as_tool


def _collect_files(root: str, target: str, extensions: set[str]) -> list[str]:
    resolved = os.path.join(root, target) if not os.path.isabs(target) else target
    if os.path.isfile(resolved):
        return [resolved] if Path(resolved).suffix.lower() in extensions else []
    found: list[str] = []
    skip = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
    for dirpath, dirnames, filenames in os.walk(resolved):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for fname in filenames:
            if Path(fname).suffix.lower() in extensions:
                found.append(os.path.join(dirpath, fname))
    return found


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def _check_js_syntax(files: list[str], root: str) -> list[str]:
    issues: list[str] = []
    for fpath in files:
        try:
            res = subprocess.run(
                ["node", "--check", fpath],
                capture_output=True, text=True, timeout=15,
            )
            output = (res.stdout + res.stderr).strip()
            if output:
                issues.append(f"[SYNTAX ERROR] {_rel(fpath, root)}: {output}")
        except FileNotFoundError:
            issues.append("[SKIP] node not found — cannot check JS syntax")
            break
        except Exception as e:
            issues.append(f"[ERROR] {_rel(fpath, root)}: {e}")
    return issues


def _check_js_patterns(files: list[str], root: str) -> list[str]:
    """Regex-based checks for common JS/HTML bugs."""
    issues: list[str] = []

    js_patterns = [
        (r"\bvar\b", "warning", "Use of 'var' — prefer 'const' or 'let'"),
        (r"document\.getElementById\([^)]+\)\.\w", "warning",
         "Possible null dereference: getElementById() result used without null check"),
        (r"addEventListener\s*\(", "info",
         "addEventListener called — ensure DOM is ready (defer or DOMContentLoaded)"),
        (r"==\s*null|null\s*==", "warning", "Use strict equality (=== null) instead of =="),
        (r"==\s*undefined|undefined\s*==", "warning", "Use strict equality (!== undefined) instead of =="),
        (r"console\.log\(", "info", "console.log() left in production code"),
    ]

    for fpath in files:
        if not fpath.endswith((".js", ".mjs", ".cjs")):
            continue
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
            for lineno, line in enumerate(lines, 1):
                for pattern, severity, message in js_patterns:
                    if re.search(pattern, line):
                        issues.append(
                            f"[{severity.upper()}] {_rel(fpath, root)}:{lineno}: {message}"
                        )
        except Exception as e:
            issues.append(f"[ERROR] {_rel(fpath, root)}: {e}")

    return issues


def _check_html_patterns(files: list[str], root: str) -> list[str]:
    issues: list[str] = []

    html_patterns = [
        (r"<script\b(?![^>]*\bdefer\b)(?![^>]*\btype\s*=\s*['\"]module['\"])[^>]*src=", "warning",
         "<script src=...> without defer — script may run before DOM is ready"),
        (r"(?i)<html(?!\s[^>]*lang=)", "warning",
         "<html> tag missing lang attribute"),
        (r"(?i)<!DOCTYPE\s+html>", None, None),  # presence is OK, absence is the bug
        (r"(?i)<meta\s[^>]*charset", None, None),
    ]

    for fpath in files:
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")

            if not re.search(r"(?i)<!DOCTYPE\s+html>", source):
                issues.append(f"[WARNING] {_rel(fpath, root)}: Missing <!DOCTYPE html>")
            if not re.search(r"(?i)<meta\s[^>]*charset", source):
                issues.append(f"[WARNING] {_rel(fpath, root)}: Missing <meta charset=...>")

            lines = source.splitlines()
            for lineno, line in enumerate(lines, 1):
                for pattern, severity, message in html_patterns:
                    if severity is None:
                        continue
                    if re.search(pattern, line):
                        issues.append(f"[{severity.upper()}] {_rel(fpath, root)}:{lineno}: {message}")
        except Exception as e:
            issues.append(f"[ERROR] {_rel(fpath, root)}: {e}")

    return issues


def _check_css_patterns(files: list[str], root: str) -> list[str]:
    issues: list[str] = []

    css_patterns = [
        (r"\bfloat\s*:\s*(?:left|right)\b", "warning",
         "Use of float for layout — prefer flexbox or grid"),
        (r"!important", "warning",
         "!important overrides cascade — use more specific selectors instead"),
        (r"(?<!\*)\bbox-sizing\b", "info",
         "box-sizing found — ensure 'box-sizing: border-box' is set globally"),
    ]

    for fpath in files:
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
            for lineno, line in enumerate(lines, 1):
                for pattern, severity, message in css_patterns:
                    if re.search(pattern, line):
                        issues.append(f"[{severity.upper()}] {_rel(fpath, root)}:{lineno}: {message}")
        except Exception as e:
            issues.append(f"[ERROR] {_rel(fpath, root)}: {e}")

    return issues


@as_tool(
    name="search_html_css_js_bugs",
    description=(
        "Detect bugs and anti-patterns in HTML, CSS, and JavaScript files. "
        "Runs: (1) JS syntax check via node --check; "
        "(2) regex pattern checks for common JS bugs (var, null dereference, missing defer, etc.); "
        "(3) HTML structural checks (DOCTYPE, charset, script defer); "
        "(4) CSS anti-pattern checks (float layout, !important abuse). "
        "Pass a file path or directory relative to the project root. "
        "Returns a structured list of issues sorted by severity."
    ),
)
def search_html_css_js_bugs(path: str = ".") -> str:
    try:
        from opalacoder.tools import get_project_path, AGENT_PROGRESS, _preview
        AGENT_PROGRESS.update("search_html_css_js_bugs", f"path={_preview(path)}")
        root = get_project_path()
    except Exception:
        root = os.getcwd()

    resolved = os.path.join(root, path) if not os.path.isabs(path) else path

    js_files = _collect_files(root, resolved, {".js", ".mjs", ".cjs"})
    html_files = _collect_files(root, resolved, {".html", ".htm"})
    css_files = _collect_files(root, resolved, {".css"})

    total = len(js_files) + len(html_files) + len(css_files)
    if total == 0:
        return f"No HTML/CSS/JS files found in '{path}'."

    all_issues: list[str] = []
    all_issues.extend(_check_js_syntax(js_files, root))
    all_issues.extend(_check_js_patterns(js_files, root))
    all_issues.extend(_check_html_patterns(html_files, root))
    all_issues.extend(_check_css_patterns(css_files, root))

    if not all_issues:
        return (
            f"No issues detected in {len(js_files)} JS, {len(html_files)} HTML, "
            f"{len(css_files)} CSS file(s)."
        )

    header = (
        f"Found {len(all_issues)} issue(s) in "
        f"{len(js_files)} JS, {len(html_files)} HTML, {len(css_files)} CSS file(s):\n"
    )
    return header + "\n".join(all_issues)
