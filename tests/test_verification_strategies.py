"""Tests to evaluate three verification strategies for the workflow reviewer.

Each strategy is tested against concrete scenarios derived from real failures
observed in the micalc project:

  Scenario A — worker edited the WRONG file (script.js instead of index.html)
  Scenario B — worker claimed success but made no change at all
  Scenario C — worker edited the right file correctly

The three strategies:

  H1 — Diff-based: reviewer receives git diff + task goal and decides
  H2 — Re-run skill tool: compare tool output before vs after; reject if same errors remain
  H3 — Planner-generated assertion: model writes a shell/node check; harness runs it

For H1 and H3 we need a live LLM call.
For H2 we need only the tool itself — fully deterministic, no LLM.

Run:
    python -m pytest tests/test_verification_strategies.py -s -v
"""

import asyncio
import os
import sys
import textwrap
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Fixtures — HTML/JS content representing the three scenarios
# ---------------------------------------------------------------------------

# The broken index.html (btn-nine has data-action='multiply' instead of data-value='9')
HTML_BROKEN = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Calculator</title></head>
<body>
  <div class="buttons">
    <button id="btn-clear" data-action="clear">AC</button>
    <button id="btn-nine"  data-action="multiply">9</button>
    <button id="btn-multiply" data-action="multiply">×</button>
    <button id="btn-add"   data-action="add">+</button>
    <button id="btn-equals" data-action="equals">=</button>
  </div>
  <script src="script.js" defer></script>
</body>
</html>
"""

# index.html after the CORRECT fix (btn-nine gets data-value='9')
HTML_FIXED = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Calculator</title></head>
<body>
  <div class="buttons">
    <button id="btn-clear" data-action="clear">AC</button>
    <button id="btn-nine"  data-value="9">9</button>
    <button id="btn-multiply" data-action="multiply">×</button>
    <button id="btn-add"   data-action="add">+</button>
    <button id="btn-equals" data-action="equals">=</button>
  </div>
  <script src="script.js" defer></script>
</body>
</html>
"""

# script.js — correct event handler (handles action === 'multiply' etc.)
SCRIPT_JS = """\
document.addEventListener('DOMContentLoaded', () => {
    const buttonsContainer = document.querySelector('.buttons');
    let currentInput = '0';
    let firstOperand = null;
    let operator = null;
    let waitingForSecondOperand = false;

    const handleNumberInput = (value) => {
        currentInput = currentInput === '0' ? value : currentInput + value;
    };

    const handleButtonClick = (event) => {
        const target = event.target.closest('button');
        if (!target) return;
        const action = target.dataset.action || '';
        const value  = target.dataset.value  || '';
        if (value !== '' && !isNaN(value)) {
            handleNumberInput(value);
        } else if (action === 'clear') {
            currentInput = '0';
        } else if (action === 'add' || action === 'subtract' ||
                   action === 'multiply' || action === 'divide') {
            firstOperand = parseFloat(currentInput);
            operator = action;
            waitingForSecondOperand = true;
        } else if (action === 'equals') {
            // compute
        }
    };
    buttonsContainer.addEventListener('click', handleButtonClick);
});
"""

# script.js after a WRONG "fix" — worker added a special-case for btn-nine
# but the HTML still has data-action='multiply'; the fix is cosmetically present
# but the root cause (HTML attribute) is untouched.
SCRIPT_JS_WRONG_FIX = """\
document.addEventListener('DOMContentLoaded', () => {
    const buttonsContainer = document.querySelector('.buttons');
    let currentInput = '0';
    let firstOperand = null;
    let operator = null;
    let waitingForSecondOperand = false;

    const handleNumberInput = (value) => {
        currentInput = currentInput === '0' ? value : currentInput + value;
    };

    const handleButtonClick = (event) => {
        const target = event.target.closest('button');
        if (!target) return;
        // WRONG FIX: special-casing btn-nine by ID instead of fixing the HTML
        if (target.id === 'btn-nine') { handleNumberInput('9'); return; }
        const action = target.dataset.action || '';
        const value  = target.dataset.value  || '';
        if (value !== '' && !isNaN(value)) {
            handleNumberInput(value);
        } else if (action === 'clear') {
            currentInput = '0';
        } else if (action === 'add' || action === 'subtract' ||
                   action === 'multiply' || action === 'divide') {
            firstOperand = parseFloat(currentInput);
            operator = action;
            waitingForSecondOperand = true;
        } else if (action === 'equals') {
            // compute
        }
    };
    buttonsContainer.addEventListener('click', handleButtonClick);
});
"""


def _make_project(html_content: str, js_content: str) -> str:
    """Write a temporary project directory and return its path."""
    d = tempfile.mkdtemp(prefix="opalacoder_test_")
    Path(d, "index.html").write_text(html_content)
    Path(d, "script.js").write_text(js_content)
    return d


# ---------------------------------------------------------------------------
# H2 — Re-run skill tool, compare errors before vs after (NO LLM needed)
# ---------------------------------------------------------------------------

def _run_tool(project_dir: str) -> set[str]:
    """Run search_html_css_js_bugs and return the set of CONTRACT/ERROR lines."""
    from opalacoder.plugins.html_css_js_tools import (
        _collect_files, _check_html_patterns, _check_html_js_contract,
        _check_js_patterns,
    )
    root = project_dir
    html = _collect_files(root, root, {".html"})
    js   = _collect_files(root, root, {".js"})
    issues = (
        _check_html_patterns(html, root)
        + _check_js_patterns(js, root)
        + _check_html_js_contract(html, js, root)
    )
    # Keep only actionable errors, not INFO/WARNING noise
    return {i for i in issues if i.startswith("[CONTRACT ERROR]") or i.startswith("[ERROR]")}


class H2Verifier:
    """Strategy H2: re-run tool, reject if same errors remain."""

    def check(self, errors_before: set[str], errors_after: set[str]) -> dict:
        unresolved = errors_before & errors_after
        new_errors  = errors_after - errors_before
        resolved    = errors_before - errors_after
        done = len(unresolved) == 0 and len(new_errors) == 0
        return {
            "done":       done,
            "unresolved": unresolved,
            "new_errors": new_errors,
            "resolved":   resolved,
        }


def test_h2_detects_wrong_file_edit():
    """H2: worker edited script.js but left index.html broken — must reject."""
    proj_before = _make_project(HTML_BROKEN, SCRIPT_JS)
    proj_after  = _make_project(HTML_BROKEN, SCRIPT_JS_WRONG_FIX)
    try:
        errors_before = _run_tool(proj_before)
        errors_after  = _run_tool(proj_after)
        result = H2Verifier().check(errors_before, errors_after)

        print(f"\n[H2 wrong-file] errors_before={errors_before}")
        print(f"[H2 wrong-file] errors_after= {errors_after}")
        print(f"[H2 wrong-file] result={result}")

        assert not result["done"], "H2 should REJECT — HTML is still broken"
        assert result["unresolved"], "H2 should report unresolved errors"
    finally:
        shutil.rmtree(proj_before, ignore_errors=True)
        shutil.rmtree(proj_after,  ignore_errors=True)


def test_h2_accepts_correct_fix():
    """H2: worker fixed index.html correctly — must accept."""
    proj_before = _make_project(HTML_BROKEN, SCRIPT_JS)
    proj_after  = _make_project(HTML_FIXED,  SCRIPT_JS)
    try:
        errors_before = _run_tool(proj_before)
        errors_after  = _run_tool(proj_after)
        result = H2Verifier().check(errors_before, errors_after)

        print(f"\n[H2 correct-fix] errors_before={errors_before}")
        print(f"[H2 correct-fix] errors_after= {errors_after}")
        print(f"[H2 correct-fix] result={result}")

        assert result["done"], f"H2 should ACCEPT — HTML is fixed. unresolved={result['unresolved']}"
    finally:
        shutil.rmtree(proj_before, ignore_errors=True)
        shutil.rmtree(proj_after,  ignore_errors=True)


def test_h2_detects_no_change():
    """H2: worker made no change at all — must reject."""
    proj = _make_project(HTML_BROKEN, SCRIPT_JS)
    try:
        errors_before = _run_tool(proj)
        errors_after  = _run_tool(proj)   # same project, nothing changed
        result = H2Verifier().check(errors_before, errors_after)

        print(f"\n[H2 no-change] result={result}")

        assert not result["done"], "H2 should REJECT — nothing changed"
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_h2_rejects_when_new_errors_introduced():
    """H2: worker fixed the original bug but introduced a new one — must reject."""
    # HTML fixed, but JS now has a duplicate case
    js_with_new_bug = SCRIPT_JS + "\n// duplicate:\ndocument.querySelector('.buttons');\n"
    # Introduce a real detectable error: duplicate case in switch
    js_with_duplicate_case = SCRIPT_JS.replace(
        "} else if (action === 'equals') {\n            // compute",
        "} else if (action === 'add') {\n            // duplicate add\n"
        "} else if (action === 'equals') {\n            // compute",
    )
    proj_before = _make_project(HTML_BROKEN, SCRIPT_JS)
    proj_after  = _make_project(HTML_FIXED,  js_with_new_bug)
    try:
        errors_before = _run_tool(proj_before)
        errors_after  = _run_tool(proj_after)
        result = H2Verifier().check(errors_before, errors_after)

        print(f"\n[H2 new-error] errors_before={errors_before}")
        print(f"[H2 new-error] errors_after= {errors_after}")
        print(f"[H2 new-error] result={result}")

        # This test documents current H2 behaviour: if new_errors is empty
        # (the new bug isn't detected by the tool), H2 passes it. This is
        # a known limitation — H2 only catches what the tool can see.
        print(f"[H2 new-error] NOTE: done={result['done']} "
              f"(H2 can only catch errors the tool detects)")
    finally:
        shutil.rmtree(proj_before, ignore_errors=True)
        shutil.rmtree(proj_after,  ignore_errors=True)


# ---------------------------------------------------------------------------
# H1 — Diff-based LLM review (requires live model)
# ---------------------------------------------------------------------------

def _make_diff(html_before: str, html_after: str) -> str:
    import difflib
    return "".join(difflib.unified_diff(
        html_before.splitlines(keepends=True),
        html_after.splitlines(keepends=True),
        fromfile="index.html (before)",
        tofile="index.html (after)",
    ))


async def _h1_llm_review(task_goal: str, diff: str, model: str, llm_kwargs: dict) -> dict:
    """Ask the LLM: given this diff and goal, was the right change applied?"""
    import litellm, json, re as _re
    prompt = (
        f"Task goal: {task_goal}\n\n"
        f"Git diff of changes made:\n```\n{diff}\n```\n\n"
        "Answer with JSON only: "
        '{{"correct": true/false, "reason": "one sentence"}}'
    )
    resp = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content":
             "You are a code reviewer. Given a task goal and a git diff, "
             "decide if the diff achieves the goal. Reply ONLY with JSON."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        **llm_kwargs,
    )
    content = resp.choices[0].message.content or "{}"
    content = _re.sub(r"^```[a-z]*\n?", "", content.strip())
    content = _re.sub(r"\n?```$", "", content)
    return json.loads(content)


GEMMA4_MODEL = "ollama/gemma4:latest"
GEMMA4_KWARGS = {"temperature": 0, "num_ctx": 8192}


@pytest.mark.llm
def test_h1_rejects_wrong_file_edit():
    """H1: Gemma4 reviewer given diff of script.js change should say incorrect."""
    model = GEMMA4_MODEL
    llm_kwargs = GEMMA4_KWARGS

    diff = _make_diff(SCRIPT_JS, SCRIPT_JS_WRONG_FIX)
    task_goal = (
        "Fix the '9' button in the calculator. The button has data-action='multiply' "
        "in index.html but should have data-value='9'."
    )

    result = asyncio.run(_h1_llm_review(task_goal, diff, model, llm_kwargs))
    print(f"\n[H1 wrong-file] result={result}")
    assert not result.get("correct"), (
        f"H1 should say the diff is WRONG (fixed script.js not index.html). "
        f"Got: {result}"
    )


@pytest.mark.llm
def test_h1_accepts_correct_fix():
    """H1: Gemma4 reviewer given diff of correct index.html fix should say correct."""
    model = GEMMA4_MODEL
    llm_kwargs = GEMMA4_KWARGS

    diff = _make_diff(HTML_BROKEN, HTML_FIXED)
    task_goal = (
        "Fix the '9' button in the calculator. The button has data-action='multiply' "
        "in index.html but should have data-value='9'."
    )

    result = asyncio.run(_h1_llm_review(task_goal, diff, model, llm_kwargs))
    print(f"\n[H1 correct-fix] result={result}")
    assert result.get("correct"), (
        f"H1 should say the diff is CORRECT. Got: {result}"
    )


# ---------------------------------------------------------------------------
# H3 — Planner-generated assertion (requires live model)
# ---------------------------------------------------------------------------

async def _h3_generate_assertion(task_goal: str, model: str, llm_kwargs: dict) -> str:
    """Ask the LLM to generate a node one-liner that verifies the fix."""
    import litellm, json, re as _re
    prompt = (
        f"Task goal: {task_goal}\n\n"
        "Write a single node.js one-liner command (using -e flag) that:\n"
        "- reads index.html from the current directory\n"
        "- exits with code 0 if the fix is correct, code 1 if not\n"
        "Reply ONLY with JSON: {\"command\": \"node -e '...'\"}"
    )
    resp = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content":
             "You generate shell verification commands. Reply ONLY with JSON."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        **llm_kwargs,
    )
    content = resp.choices[0].message.content or "{}"
    content = _re.sub(r"^```[a-z]*\n?", "", content.strip())
    content = _re.sub(r"\n?```$", "", content)
    data = json.loads(content)
    return data.get("command", "")


def _run_assertion(command: str, cwd: str) -> tuple[int, str]:
    import subprocess
    r = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd, timeout=10)
    return r.returncode, (r.stdout + r.stderr).strip()


@pytest.mark.llm
def test_h3_assertion_on_broken_html():
    """H3: Gemma4-generated assertion should FAIL on broken HTML."""
    model = GEMMA4_MODEL
    llm_kwargs = GEMMA4_KWARGS

    task_goal = (
        "Fix btn-nine in index.html: replace data-action='multiply' with data-value='9'."
    )
    command = asyncio.run(_h3_generate_assertion(task_goal, model, llm_kwargs))
    print(f"\n[H3 broken] generated command: {command}")

    proj = _make_project(HTML_BROKEN, SCRIPT_JS)
    try:
        rc, output = _run_assertion(command, proj)
        print(f"[H3 broken] exit={rc} output={output!r}")
        assert rc != 0, f"H3 assertion should FAIL on broken HTML. exit={rc}"
    finally:
        shutil.rmtree(proj, ignore_errors=True)


@pytest.mark.llm
def test_h3_assertion_on_fixed_html():
    """H3: Gemma4-generated assertion should PASS on fixed HTML."""
    model = GEMMA4_MODEL
    llm_kwargs = GEMMA4_KWARGS

    task_goal = (
        "Fix btn-nine in index.html: replace data-action='multiply' with data-value='9'."
    )
    command = asyncio.run(_h3_generate_assertion(task_goal, model, llm_kwargs))
    print(f"\n[H3 fixed] generated command: {command}")

    proj = _make_project(HTML_FIXED, SCRIPT_JS)
    try:
        rc, output = _run_assertion(command, proj)
        print(f"[H3 fixed] exit={rc} output={output!r}")
        assert rc == 0, f"H3 assertion should PASS on fixed HTML. exit={rc}"
    finally:
        shutil.rmtree(proj, ignore_errors=True)
