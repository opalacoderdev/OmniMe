import re

from abcode.executor import SharedContext, _build_task, _extract_context_regex
from abcode.subplan import Subplan


def test_build_task_includes_project_dir_instructions():
    sp = Subplan(
        id="SP-1",
        phase="init",
        objective="Initialize calculator app",
        prerequisites=[],
        steps=["Create basic HTML/CSS/JS files"],
        completion_criterion="Project files exist",
    )

    prompt = _build_task(
        sp,
        original_request="crie um app de calculadora",
        context="No previous steps executed yet.",
        global_skills_context="",
        cwd="/workspace",
        project_dir="calculator-app",
    )

    assert "Target Project Directory (where you must put your files): calculator-app" in prompt
    assert "working directory already set to the project root" in prompt
    assert "pathlib.Path" in prompt or "Path(" in prompt


def test_extract_context_regex_uses_explicit_project_dir():
    current_state = "No previous steps executed yet. Project is starting from scratch."
    output = "PROJECT_DIR: calculator-app\nCreated calculator-app/index.html\n"

    new_state = _extract_context_regex(current_state, output, "SP-1")

    assert new_state is not None
    assert "PROJECT_DIR: calculator-app" in new_state
    assert "Completed: SP-1" in new_state
    assert "Files: calculator-app/index.html" in new_state


def test_extract_context_regex_infers_project_dir_from_nested_paths():
    current_state = "No previous steps executed yet. Project is starting from scratch."
    output = "Wrote calculator-app/index.html\nWrote calculator-app/style.css\n"

    new_state = _extract_context_regex(current_state, output, "SP-2")

    assert new_state is not None
    assert "PROJECT_DIR: calculator-app" in new_state
    assert "Completed: SP-2" in new_state
    assert "Files: calculator-app/index.html, calculator-app/style.css" in new_state


def test_extract_context_regex_preserves_existing_project_dir():
    current_state = "PROJECT_DIR: calculator-app\nCompleted: SP-1"
    output = "Wrote calculator-app/index.html\n"

    new_state = _extract_context_regex(current_state, output, "SP-2")

    assert new_state is not None
    assert new_state.startswith("PROJECT_DIR: calculator-app")
    assert "Completed: SP-2" in new_state


def test_extract_context_regex_defaults_to_root_when_no_project_dir_found():
    current_state = "No previous steps executed yet. Project is starting from scratch."
    output = "Created index.html\nCreated style.css\n"

    new_state = _extract_context_regex(current_state, output, "SP-3")

    assert new_state is not None
    assert "PROJECT_DIR: ." in new_state
    assert "Completed: SP-3" in new_state
    assert "Files: index.html, style.css" in new_state


def test_project_dir_persists_between_subplans():
    shared_state = SharedContext("No previous steps executed yet. Project is starting from scratch.")
    first_output = "PROJECT_DIR: calculator-app\nCreated calculator-app/index.html\n"

    updated_state = _extract_context_regex(shared_state.value, first_output, "SP-1")
    assert updated_state is not None
    shared_state.value = updated_state
    assert "PROJECT_DIR: calculator-app" in shared_state.value

    second_sp = Subplan(
        id="SP-2",
        phase="features",
        objective="Add calculator functionality",
        prerequisites=["SP-1"],
        steps=["Hook up buttons to calculator logic"],
        completion_criterion="Calculator buttons work",
    )

    prompt = _build_task(
        second_sp,
        original_request="crie um app de calculadora",
        context=shared_state.value,
        global_skills_context="",
        cwd="/workspace",
        project_dir="calculator-app",
    )

    assert "Target Project Directory (where you must put your files): calculator-app" in prompt
    assert "working directory already set to the project root" in prompt
    assert "calculator-app" in prompt


def test_extract_context_regex_infers_project_dir_from_bare_folder_creation():
    current_state = "No previous steps executed yet. Project is starting from scratch."
    output = "Created calculator-app\n"

    new_state = _extract_context_regex(current_state, output, "SP-4")

    assert new_state is not None
    assert "PROJECT_DIR: calculator-app" in new_state
    assert "Completed: SP-4" in new_state
    assert "Files:" not in new_state or "calculator-app" not in new_state
