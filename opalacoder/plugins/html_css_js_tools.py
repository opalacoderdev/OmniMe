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
            # Detect duplicate case labels within switch blocks
            _check_duplicate_cases(fpath, lines, root, issues)
        except Exception as e:
            issues.append(f"[ERROR] {_rel(fpath, root)}: {e}")

    return issues


def _check_duplicate_cases(fpath: str, lines: list[str], root: str, issues: list[str]) -> None:
    """Detect duplicate case labels inside switch blocks."""
    case_pat = re.compile(r"""^\s*case\s+(['"`])([^'"`]+)\1\s*:""")
    seen: dict[str, int] = {}  # label -> first lineno
    depth = 0  # brace depth inside switch
    in_switch = False
    switch_pat = re.compile(r"\bswitch\s*\(")

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if switch_pat.search(line):
            in_switch = True
            seen = {}
            depth = 0
        if in_switch:
            depth += line.count("{") - line.count("}")
            if depth <= 0 and lineno > 1:
                in_switch = False
                seen = {}
                continue
            m = case_pat.match(line)
            if m:
                label = m.group(2)
                if label in seen:
                    rel = _rel(fpath, root)
                    issues.append(
                        f"[ERROR] {rel}:{lineno}: duplicate case '{label}' in switch "
                        f"(first seen at line {seen[label]}) — "
                        f"FIX REQUIRED: delete the duplicate case block at line {lineno} using edit_file"
                    )
                else:
                    seen[label] = lineno


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

            # Detect buttons whose visible label is a digit (0-9) or '.'
            # but are missing data-value — they will never reach handleNumberInput.
            btn_full = re.compile(
                r"<button\b([^>]*)>([\s\S]*?)</button>",
                re.IGNORECASE,
            )
            for m in btn_full.finditer(source):
                attrs_str = m.group(1)
                label = m.group(2).strip()
                if not re.match(r'^[0-9.]$', label):
                    continue
                has_value = bool(re.search(r'data-value\s*=', attrs_str, re.IGNORECASE))
                if not has_value:
                    id_m = re.search(r"""\bid\s*=\s*["']([^"']*)["']""", attrs_str, re.IGNORECASE)
                    elem_id = id_m.group(1) if id_m else "unknown"
                    action_m = re.search(r"""data-action\s*=\s*["']([^"']*)["']""", attrs_str, re.IGNORECASE)
                    action = action_m.group(1) if action_m else None
                    lineno = source[:m.start()].count("\n") + 1
                    rel = _rel(fpath, root)
                    if action:
                        issues.append(
                            f"[CONTRACT ERROR] {rel}:{lineno}: button#{elem_id} has label '{label}' "
                            f"but data-action='{action}' instead of data-value='{label}'. "
                            f"FIX REQUIRED IN HTML: replace data-action='{action}' with data-value='{label}' "
                            f"so the JS routes it as a number input, not as an operator."
                        )
                    else:
                        issues.append(
                            f"[CONTRACT ERROR] {rel}:{lineno}: button#{elem_id} has label '{label}' "
                            f"but no data-value attribute — it will never be routed as a number input. "
                            f"FIX REQUIRED IN HTML: add data-value='{label}' to this button."
                        )
        except Exception as e:
            issues.append(f"[ERROR] {_rel(fpath, root)}: {e}")

    return issues


def _extract_html_button_contracts(html_files: list[str]) -> list[dict]:
    """Extract data-action and data-value from every <button> in the HTML files.

    Returns a list of dicts: {file, lineno, element, action, value}
    where action/value are the raw attribute strings (or None if absent).
    """
    contracts: list[dict] = []
    # Match any interactive element that could carry data-* attributes
    tag_pattern = re.compile(
        r"<(button|input|a|select)\b([^>]*)>",
        re.IGNORECASE | re.DOTALL,
    )
    data_action = re.compile(r"""data-action\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
    data_value  = re.compile(r"""data-value\s*=\s*["']([^"']*)["']""",  re.IGNORECASE)
    elem_id     = re.compile(r"""\bid\s*=\s*["']([^"']*)["']""",         re.IGNORECASE)

    for fpath in html_files:
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")
            for m in tag_pattern.finditer(source):
                attrs = m.group(2)
                action_m = data_action.search(attrs)
                value_m  = data_value.search(attrs)
                id_m     = elem_id.search(attrs)
                if action_m or value_m:
                    lineno = source[: m.start()].count("\n") + 1
                    contracts.append({
                        "file":    fpath,
                        "lineno":  lineno,
                        "element": m.group(1).lower(),
                        "id":      id_m.group(1) if id_m else None,
                        "action":  action_m.group(1) if action_m else None,
                        "value":   value_m.group(1)  if value_m  else None,
                    })
        except Exception:
            pass
    return contracts


def _extract_js_handled_actions(js_files: list[str]) -> tuple[set[str], set[str]]:
    """Extract the set of action strings and value strings that the JS handles.

    Scans for patterns like:
      action === 'X'  /  action == 'X'
      ['a','b'].includes(action)
      case 'X':
      value === 'X'  /  value == 'X'

    Returns (handled_actions, handled_values).
    """
    handled_actions: set[str] = set()
    handled_values:  set[str] = set()

    # action === 'X' or action == 'X'
    action_eq   = re.compile(r"""action\s*={2,3}\s*["']([^"']+)["']""")
    # ['a','b','c'].includes(action)
    action_incl = re.compile(r"""\[([^\]]+)\]\s*\.\s*includes\s*\(\s*action\s*\)""")
    # case 'X': inside a switch — heuristic, may catch non-action cases too
    case_str    = re.compile(r"""case\s+["']([^"']+)["']\s*:""")
    # value === 'X'
    value_eq    = re.compile(r"""value\s*={2,3}\s*["']([^"']+)["']""")

    for fpath in js_files:
        try:
            source = Path(fpath).read_text(encoding="utf-8", errors="replace")
            for m in action_eq.finditer(source):
                handled_actions.add(m.group(1))
            for m in action_incl.finditer(source):
                # parse the array literal: ['add','subtract',...]
                items = re.findall(r"""["']([^"']+)["']""", m.group(1))
                handled_actions.update(items)
            for m in case_str.finditer(source):
                # add to both sets — the switch might be on action OR op
                handled_actions.add(m.group(1))
            for m in value_eq.finditer(source):
                handled_values.add(m.group(1))
        except Exception:
            pass

    return handled_actions, handled_values


def _check_html_js_contract(html_files: list[str], js_files: list[str], root: str) -> list[str]:
    """Cross-file contract check: every data-action/data-value in HTML must be handled in JS.

    Extracts only the minimal "contract chunks" from each file — no full file content
    is needed. Reports mismatches as actionable bugs.
    """
    if not html_files or not js_files:
        return []

    contracts = _extract_html_button_contracts(html_files)
    if not contracts:
        return []

    handled_actions, handled_values = _extract_js_handled_actions(js_files)
    issues: list[str] = []

    # Numeric values and "." are always handled by the number/decimal paths —
    # only non-numeric, non-"." values need an explicit JS handler.
    _IMPLICIT = {str(i) for i in range(10)} | {"."}
    # Operator symbols that are NOT handled as actions — if used as data-value
    # for operator buttons they are a mismatch (should be data-action instead).
    _OPERATOR_SYMBOLS = {"+", "-", "*", "/", "×", "÷", "x"}

    for c in contracts:
        rel = _rel(c["file"], root)
        label = f"{c['element']}" + (f"#{c['id']}" if c["id"] else "")

        if c["action"] is not None:
            act = c["action"]
            if act and act not in handled_actions:
                issues.append(
                    f"[CONTRACT ERROR] {rel}:{c['lineno']}: "
                    f"{label} has data-action='{act}' but JS never handles action === '{act}'"
                )

        if c["value"] is not None:
            val = c["value"]
            # Flag operator symbols used as data-value — they should be data-action
            if val in _OPERATOR_SYMBOLS:
                # Determine which action name the symbol maps to
                sym_to_action = {
                    "+": "add", "-": "subtract",
                    "*": "multiply", "×": "multiply", "x": "multiply",
                    "/": "divide", "÷": "divide",
                }
                expected_action = sym_to_action.get(val, f"<handler for '{val}'>")
                issues.append(
                    f"[CONTRACT ERROR] {rel}:{c['lineno']}: "
                    f"{label} has data-value='{val}' (operator symbol) — "
                    f"JS routes this as a number/decimal, not as an operator. "
                    f"FIX REQUIRED IN HTML: in {rel} line {c['lineno']}, "
                    f"replace data-value='{val}' with data-action='{expected_action}'. "
                    f"Do NOT modify script.js — the JS already handles action === '{expected_action}'."
                )
            elif val in handled_actions and val not in handled_values:
                # An action name (e.g. "multiply", "clear") used as data-value is always wrong.
                # Determine the right fix: if the button id/label is a digit, the fix is data-value=<digit>.
                btn_label = c.get("id", "")
                # Try to infer the correct digit from the element id (e.g. btn-nine → 9)
                _word_to_digit = {
                    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
                    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
                }
                digit_hint = None
                for word, digit in _word_to_digit.items():
                    if word in (btn_label or "").lower():
                        digit_hint = digit
                        break
                if digit_hint:
                    fix_hint = f"replace data-value='{val}' with data-value='{digit_hint}'"
                else:
                    fix_hint = f"replace data-value='{val}' with data-action='{val}'"
                issues.append(
                    f"[CONTRACT ERROR] {rel}:{c['lineno']}: "
                    f"{label} has data-value='{val}' but '{val}' is a JS action name, not a numeric value — "
                    f"the button will never work as a number input. "
                    f"FIX REQUIRED IN HTML: {fix_hint}."
                )
            elif val not in _IMPLICIT and val not in handled_values:
                issues.append(
                    f"[CONTRACT WARNING] {rel}:{c['lineno']}: "
                    f"{label} has data-value='{val}' but no explicit JS handler found for this value"
                )

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


def html_css_js_reviewer(
    project_path: str,
    task_goal: str,
    related_files: list[str],
    errors_before: set[str] | None = None,
) -> dict:
    """H2 skill reviewer: re-run the bug scanner and compare with the before-snapshot.

    When errors_before is provided (the set of blocking errors captured before the
    worker ran), only errors that existed before AND still exist after count as
    unresolved — pre-existing errors unrelated to the task are ignored.

    When errors_before is None the reviewer falls back to checking whether any
    blocking errors exist at all (conservative but safe).
    """
    import os as _os

    root = project_path or _os.getcwd()

    js_files   = _collect_files(root, root, {".js", ".mjs", ".cjs"})
    html_files = _collect_files(root, root, {".html", ".htm"})

    raw_issues: list[str] = []
    raw_issues.extend(_check_js_syntax(js_files, root))
    raw_issues.extend(_check_html_patterns(html_files, root))
    raw_issues.extend(_check_html_js_contract(html_files, js_files, root))

    blocking_tags = ("[CONTRACT ERROR]", "[SYNTAX ERROR]", "[ERROR]")
    errors_after = {i.strip() for i in raw_issues if any(i.startswith(t) for t in blocking_tags)}

    if errors_before is not None:
        unresolved = errors_before & errors_after
        new_errors = errors_after - errors_before
        bad = sorted(unresolved) + sorted(new_errors)
        if bad:
            label = (
                f"{len(unresolved)} unresolved + {len(new_errors)} new error(s)"
                if unresolved and new_errors
                else (f"{len(unresolved)} error(s) still unresolved" if unresolved else f"{len(new_errors)} new error(s) introduced")
            )
            return {
                "done": False,
                "summary": f"H2 reviewer: {label} after worker ran.",
                "corrections": bad[:10],
            }
        return {"done": True, "summary": "H2 reviewer: all blocking errors resolved.", "corrections": []}

    # No before-snapshot: reject if any blocking errors remain
    blocking = sorted(errors_after)
    if blocking:
        return {
            "done": False,
            "summary": f"H2 reviewer: {len(blocking)} blocking error(s) detected after worker ran.",
            "corrections": blocking[:10],
        }
    return {
        "done": True,
        "summary": "H2 reviewer: no blocking errors detected — task accepted.",
        "corrections": [],
    }


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

    js_files   = _collect_files(root, resolved, {".js", ".mjs", ".cjs"})
    html_files = _collect_files(root, resolved, {".html", ".htm"})
    css_files  = _collect_files(root, resolved, {".css"})

    # Cross-file contract analysis needs both JS and HTML.
    # When path points to a single file (or a directory with no HTML), expand
    # the HTML and JS search to the entire project so the contract check can
    # cross-reference all files — without sending any full file to the LLM.
    contract_js_files   = js_files
    contract_html_files = html_files
    if os.path.isfile(resolved) or not html_files or not js_files:
        contract_js_files   = _collect_files(root, root, {".js", ".mjs", ".cjs"})
        contract_html_files = _collect_files(root, root, {".html", ".htm"})

    total = len(js_files) + len(html_files) + len(css_files)
    if total == 0:
        return f"No HTML/CSS/JS files found in '{path}'."

    all_issues: list[str] = []
    all_issues.extend(_check_js_syntax(js_files, root))
    all_issues.extend(_check_js_patterns(js_files, root))
    all_issues.extend(_check_html_patterns(html_files, root))
    all_issues.extend(_check_css_patterns(css_files, root))
    all_issues.extend(_check_html_js_contract(contract_html_files, contract_js_files, root))

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
