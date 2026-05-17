"""Tests to detect the 'files land in project root' bug in the deterministic workflow.

Root cause: SubplanExecutionBlock.run() defaults project_dir to "." when SharedContext
has no PROJECT_DIR entry yet (which is always true for SP-1). This causes the LLM-generated
code to write files directly into the current working directory instead of a subdirectory.

A second compounding bug: _extract_context_regex may infer different directory names from
each subplan's stdout, causing inconsistent project dirs across subplans.
"""

import os
import re
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from abcode.executor import SharedContext, SubplanExecutionBlock, _build_task, _extract_context_regex, _infer_project_dir_from_request
from abcode.subplan import Subplan


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_subplan(sp_id: str, objective: str = "do something") -> Subplan:
    return Subplan(
        id=sp_id,
        phase="init",
        objective=objective,
        prerequisites=[],
        steps=["step 1"],
        completion_criterion="done",
    )


# ---------------------------------------------------------------------------
# Bug 1: project_dir defaults to "." for SP-1, causing files to land in root
# ---------------------------------------------------------------------------

def test_sp1_gets_dot_as_project_dir_when_shared_state_has_no_project_dir():
    """Reproduces Bug 1: The first subplan always receives project_dir='.'
    because SharedContext starts without a PROJECT_DIR line.
    This is the direct cause of files landing in the project root.
    """
    initial_state = "No previous steps executed yet. Project is starting from scratch."
    shared_state = SharedContext(initial_state)

    # Simulate what SubplanExecutionBlock.run() does to determine project_dir
    project_dir_match = "."
    if shared_state.value:
        match = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', shared_state.value)
        if match:
            project_dir_match = match.group(1).strip()

    # BUG: project_dir is "." so the prompt will tell the LLM to write to "."
    assert project_dir_match == ".", (
        "Expected project_dir to default to '.' (the bug). "
        "If this assertion fails, the bug was already fixed."
    )

    prompt = _build_task(
        _make_subplan("SP-1", "Initialize calculator app"),
        original_request="create a calculator app",
        context=initial_state,
        global_skills_context="",
        cwd="/workspace",
        project_dir=project_dir_match,
    )

    # The generated prompt tells the LLM to write files into "." (project root)
    assert "Target Project Directory (where you must put your files): ." in prompt, (
        "SP-1 prompt instructs the LLM to write into the project root directory."
    )


def test_files_created_in_root_when_project_dir_is_dot():
    """Integration: when project_dir='.', executing the generated code
    puts files directly in the current working directory (the project root).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Simulate the code the LLM would generate when project_dir="."
            code = textwrap.dedent("""\
                from pathlib import Path
                project_dir = "."
                Path(project_dir).mkdir(parents=True, exist_ok=True)
                Path(f"{project_dir}/index.html").write_text("<html></html>")
                Path(f"{project_dir}/styles.css").write_text("body {}")
                print("Created index.html")
                print("Created styles.css")
            """)
            exec(compile(code, "<string>", "exec"))

            # Files land directly in tmpdir (simulating the project root)
            assert (Path(tmpdir) / "index.html").exists(), "index.html in project root — this is the bug"
            assert (Path(tmpdir) / "styles.css").exists(), "styles.css in project root — this is the bug"

            # The desired behavior: files should be inside a named subdirectory
            subdirs = [p for p in Path(tmpdir).iterdir() if p.is_dir()]
            assert len(subdirs) == 0, (
                "No subdirectory was created — files went straight to root. "
                "Fix: pass a named project_dir (e.g. 'calculator-app') for SP-1."
            )
        finally:
            os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Bug 2: inconsistent project dir across subplans (regex infers different names)
# ---------------------------------------------------------------------------

def test_inconsistent_project_dir_across_subplans():
    """Reproduces Bug 2: _extract_context_regex may infer different directory
    names from different subplans' stdout, causing each subplan to write to
    a different directory.
    """
    initial_state = "No previous steps executed yet. Project is starting from scratch."

    # SP-1 prints "calc/" style output
    sp1_output = "Created calc/index.html\nCreated calc/style.css\n"
    state_after_sp1 = _extract_context_regex(initial_state, sp1_output, "SP-1")
    assert state_after_sp1 is not None
    dir_after_sp1 = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', state_after_sp1).group(1).strip()

    # SP-2 prints "calculator/" style output (LLM hallucinated a different name)
    sp2_output = "Writing calculator/app.js\nWriting calculator/style.css\n"
    state_after_sp2 = _extract_context_regex(state_after_sp1, sp2_output, "SP-2")
    assert state_after_sp2 is not None
    dir_after_sp2 = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', state_after_sp2).group(1).strip()

    # This demonstrates the inconsistency bug
    assert dir_after_sp1 != dir_after_sp2, (
        f"Expected inconsistent dirs: SP-1='{dir_after_sp1}', SP-2='{dir_after_sp2}'. "
        "This is the bug — each subplan infers its own project directory."
    )


# ---------------------------------------------------------------------------
# Desired behavior: project_dir should be fixed before execution starts
# ---------------------------------------------------------------------------

def test_extract_context_regex_preserves_existing_project_dir_when_stdout_has_bare_files():
    """Fix 3: _extract_context_regex must NOT overwrite an existing PROJECT_DIR
    with '.' when the subplan's stdout only mentions root-level filenames.
    The existing canonical dir must be preserved.
    """
    canonical_dir = "calculator-app"
    initial_state = f"PROJECT_DIR: {canonical_dir}\nProject is starting from scratch."

    # SP-1 stdout only mentions bare filenames (no directory prefix)
    sp1_output = "Created index.html\nCreated styles.css\n"

    updated = _extract_context_regex(initial_state, sp1_output, "SP-1")
    assert updated is not None

    match = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', updated)
    inferred_dir = match.group(1).strip() if match else None

    assert inferred_dir == canonical_dir, (
        f"Expected PROJECT_DIR to remain '{canonical_dir}', got '{inferred_dir}'. "
        "Fix 3 should preserve the existing PROJECT_DIR when stdout has only bare filenames."
    )


def test_infer_project_dir_from_request_portuguese():
    assert _infer_project_dir_from_request("quero criar um app de calculadora") == "app-de-calculadora"


def test_infer_project_dir_from_request_english():
    # The article "a" is consumed by the regex optional article group
    assert _infer_project_dir_from_request("create a todo list app") == "todo-list-app"


def test_infer_project_dir_from_request_fallback():
    result = _infer_project_dir_from_request("calculadora")
    assert len(result) > 0
    assert " " not in result


def test_shared_context_starts_with_canonical_project_dir():
    """Fix 1+2: SharedContext must be pre-populated with PROJECT_DIR
    so SP-1 never receives project_dir='.' (the project root).
    """
    request = "quero criar um app de calculadora"
    canonical_dir = _infer_project_dir_from_request(request)
    shared_state = SharedContext(f"PROJECT_DIR: {canonical_dir}\nProject is starting from scratch.")

    match = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', shared_state.value)
    assert match is not None
    assert match.group(1).strip() == canonical_dir

    # SP-1 now gets the correct (non-root) project_dir
    project_dir_match = "."
    m = re.search(r'PROJECT_DIR:\s*([^\n\r]+)', shared_state.value)
    if m:
        project_dir_match = m.group(1).strip()

    assert project_dir_match != ".", "SP-1 should not receive '.' as project_dir after fix."
    assert project_dir_match == canonical_dir


def test_all_files_inside_subdirectory_when_project_dir_is_fixed():
    """Integration: when project_dir is fixed to a named subdir,
    all files are created inside it, not in the project root.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            project_dir = "calculator-app"

            # Simulate SP-1 code with correct project_dir
            code_sp1 = textwrap.dedent(f"""\
                from pathlib import Path
                project_dir = "{project_dir}"
                Path(project_dir).mkdir(parents=True, exist_ok=True)
                Path(f"{{project_dir}}/index.html").write_text("<html></html>")
                Path(f"{{project_dir}}/styles.css").write_text("body {{}}")
                print(f"Created {{project_dir}}/index.html")
                print(f"Created {{project_dir}}/styles.css")
            """)
            exec(compile(code_sp1, "<string>", "exec"))

            # Simulate SP-2 code with correct project_dir
            code_sp2 = textwrap.dedent(f"""\
                from pathlib import Path
                project_dir = "{project_dir}"
                Path(f"{{project_dir}}/app.js").write_text("// calculator logic")
                print(f"Created {{project_dir}}/app.js")
            """)
            exec(compile(code_sp2, "<string>", "exec"))

            # Verify: no files in project root
            root_files = [p for p in Path(tmpdir).iterdir() if p.is_file()]
            assert root_files == [], f"Files found in project root: {root_files}"

            # Verify: all files inside the named subdirectory
            subdir = Path(tmpdir) / project_dir
            assert subdir.is_dir(), f"Expected subdirectory '{project_dir}' to exist"
            created_files = list(subdir.iterdir())
            assert len(created_files) == 3, f"Expected 3 files, got: {created_files}"
        finally:
            os.chdir(original_cwd)
