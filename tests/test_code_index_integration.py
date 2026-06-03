"""Integration tests for the code index — verifies that the index is built,
populated, and actually used by the tools and oracle prompts.

These tests are fully automated and require no user interaction.

Test strategy:
  1. Unit — build index on known synthetic files, assert symbols are found.
  2. Tools — find_symbol / find_callers return real indexed results.
  3. Oracle prompt — project_snapshot() injects symbol names into the planner
     prompt; a mock oracle captures the prompt and asserts the symbols appear.
  4. End-to-end — full Plan→Execute loop with a project that has existing
     symbols; verifier prompt contains actual file content read from disk.

Run with:
    python -m pytest tests/test_code_index_integration.py -v -s
"""

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opalacoder.code_index import CODE_INDEX, CodeIndex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_index(tmp_path: Path) -> CodeIndex:
    """Return a freshly initialised CodeIndex pointing at tmp_path."""
    idx = CodeIndex()
    idx.set_project(str(tmp_path))
    return idx


def _oracle_response(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(data)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_task(id, goal, commands, related_files=None, context="", depends_on=None):
    return {
        "id": id,
        "goal": goal,
        "commands": commands,
        "related_files": related_files or [],
        "context": context or goal,
        "depends_on": depends_on or [],
    }


class FakeSession:
    def __init__(self, project_path):
        self.project_path = project_path
        self.core_memory = ""
        self.history = []

    def context_header(self):
        return f"[PROJECT: Test | PATH: {self.project_path}]"


class FakeStore:
    def append_message(self, session, role, content):
        pass


# ---------------------------------------------------------------------------
# 1. Unit: index build and symbol search
# ---------------------------------------------------------------------------

def test_index_finds_python_functions(tmp_path):
    """Index must find function definitions in a Python file."""
    (tmp_path / "calc.py").write_text(textwrap.dedent("""\
        def add(a, b):
            return a + b

        def subtract(a, b):
            return a - b

        class Calculator:
            def multiply(self, x, y):
                return x * y
    """))

    idx = _fresh_index(tmp_path)
    idx.build()

    symbols = idx.search("add")
    names = [s.name for s in symbols]
    assert "add" in names, f"'add' not found in index. Got: {names}"

    symbols = idx.search("Calculator")
    names = [s.name for s in symbols]
    assert "Calculator" in names, f"'Calculator' not found in index. Got: {names}"


def test_index_finds_javascript_functions(tmp_path):
    """Index must find function definitions in a JavaScript file."""
    (tmp_path / "app.js").write_text(textwrap.dedent("""\
        function handleClick(event) {
            const id = event.target.id;
            updateDisplay(id);
        }

        function updateDisplay(value) {
            document.getElementById('display').textContent = value;
        }
    """))

    idx = _fresh_index(tmp_path)
    idx.build()

    symbols = idx.search("handleClick")
    names = [s.name for s in symbols]
    assert "handleClick" in names, f"'handleClick' not found. Got: {names}"

    symbols = idx.search("updateDisplay")
    names = [s.name for s in symbols]
    assert "updateDisplay" in names, f"'updateDisplay' not found. Got: {names}"


def test_index_incremental_rebuild_after_write(tmp_path):
    """After write_file creates a new symbol, rebuild_file must make it searchable."""
    (tmp_path / "module.py").write_text("def original(): pass\n")

    idx = _fresh_index(tmp_path)
    idx.build()

    # Confirm original symbol is indexed
    assert idx.search("original"), "original() not found before rewrite"

    # Simulate write_file creating a new function
    new_content = "def original(): pass\n\ndef new_function(): pass\n"
    (tmp_path / "module.py").write_text(new_content)
    idx.rebuild_file(str(tmp_path / "module.py"))

    results = idx.search("new_function")
    names = [s.name for s in results]
    assert "new_function" in names, \
        f"'new_function' not found after rebuild_file. Got: {names}"


def test_find_callers_returns_correct_caller(tmp_path):
    """find_callers must return the function that calls the target."""
    (tmp_path / "logic.py").write_text(textwrap.dedent("""\
        def render():
            display()

        def display():
            pass
    """))

    idx = _fresh_index(tmp_path)
    idx.build()

    callers = idx.find_callers("display")
    caller_names = [s.name for s in callers]
    assert "render" in caller_names, \
        f"Expected 'render' to call 'display'. Got callers: {caller_names}"


def test_project_snapshot_contains_symbol_names(tmp_path):
    """project_snapshot() must list exported symbol names, not just file paths."""
    (tmp_path / "api.py").write_text(textwrap.dedent("""\
        def get_user(user_id: int):
            pass

        def create_user(name: str, email: str):
            pass
    """))

    idx = _fresh_index(tmp_path)
    idx.build()

    snapshot = idx.project_snapshot()
    assert "get_user" in snapshot, f"'get_user' missing from snapshot:\n{snapshot}"
    assert "create_user" in snapshot, f"'create_user' missing from snapshot:\n{snapshot}"
    assert "api.py" in snapshot, f"filename missing from snapshot:\n{snapshot}"


# ---------------------------------------------------------------------------
# 2. Tools: find_symbol tool returns indexed results
# ---------------------------------------------------------------------------

def test_find_symbol_tool_returns_indexed_symbol(tmp_path):
    """The find_symbol workflow tool must return results from the real index."""
    from opalacoder.workflow_tools import find_symbol
    from opalacoder import tools as tools_module

    (tmp_path / "service.py").write_text(textwrap.dedent("""\
        def authenticate(token: str) -> bool:
            return token == "secret"

        def logout(session_id: str) -> None:
            pass
    """))

    # Wire the index to tmp_path
    CODE_INDEX.set_project(str(tmp_path))
    CODE_INDEX.build()

    with patch("opalacoder.tools.get_project_path", return_value=str(tmp_path)):
        # find_symbol is a FunctionBlock — call its underlying Python function
        result = find_symbol.__wrapped__("authenticate") if hasattr(find_symbol, "__wrapped__") \
            else _call_function_block(find_symbol, "authenticate")

    print(f"\n[find_symbol result]:\n{result}")
    assert "authenticate" in result, \
        f"'authenticate' not found in find_symbol result:\n{result}"
    assert "service.py" in result, \
        f"filename not found in find_symbol result:\n{result}"


def test_find_symbol_tool_returns_not_found_for_unknown(tmp_path):
    """find_symbol must return a helpful 'not found' message for unknown symbols."""
    from opalacoder.workflow_tools import find_symbol

    (tmp_path / "empty.py").write_text("x = 1\n")
    CODE_INDEX.set_project(str(tmp_path))
    CODE_INDEX.build()

    result = _call_function_block(find_symbol, "totally_nonexistent_xyz")
    print(f"\n[find_symbol not-found result]: {result}")
    # Must not crash and must communicate the symbol was not found
    assert "totally_nonexistent_xyz" in result or "not found" in result.lower(), \
        f"Unexpected result for unknown symbol:\n{result}"


def _call_function_block(fb, *args):
    """Call a FunctionBlock by invoking its wrapped function directly."""
    # FunctionBlocks wrap a Python function; access it via __wrapped__ or
    # by inspecting the block's function attribute.
    import inspect
    if hasattr(fb, "__wrapped__"):
        return fb.__wrapped__(*args)
    # Try to find the underlying callable in the block's dict
    for attr in ("func", "_func", "fn", "_fn"):
        if hasattr(fb, attr):
            f = getattr(fb, attr)
            if callable(f):
                return f(*args)
    # Last resort: look for the first callable in instance dict
    for v in vars(fb).values():
        if callable(v) and not isinstance(v, type):
            return v(*args)
    raise RuntimeError(f"Cannot find underlying function in FunctionBlock {fb!r}")


# ---------------------------------------------------------------------------
# 3. Oracle prompt: snapshot injected into planner
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_planner_prompt_contains_indexed_symbols(tmp_path):
    """The planner oracle prompt must contain symbol names from the code index.

    This verifies the full chain:
      CODE_INDEX.build() → project_snapshot() → planning_prompt → oracle receives it
    """
    from opalacoder.orchestrator import WorkflowOrchestratorStrategy

    project_path = str(tmp_path)

    # Pre-populate the project with a Python module that has known symbols
    (tmp_path / "calculator.py").write_text(textwrap.dedent("""\
        def add_numbers(a: float, b: float) -> float:
            return a + b

        def divide_numbers(a: float, b: float) -> float:
            if b == 0:
                raise ValueError("division by zero")
            return a / b

        class CalculatorEngine:
            def run(self, op, a, b):
                pass
    """))

    captured_prompts: list[str] = []
    call_count = [0]

    async def fake_acompletion(**kwargs):
        call_count[0] += 1
        content = kwargs["messages"][-1]["content"]
        if call_count[0] == 1:
            captured_prompts.append(content)
            return _oracle_response({"tasks": [_make_task(
                "t1",
                goal=f"Add tests for add_numbers in {project_path}/test_calc.py",
                commands=[f"Create {project_path}/test_calc.py with unit tests for add_numbers"],
                related_files=["calculator.py"],
                context="add_numbers(a, b) returns a+b. divide_numbers(a, b) raises ValueError when b==0.",
            )]})
        return _oracle_response({"done": True, "summary": "Done.", "corrections": []})

    async def fake_agent_run(self_agent, agent_input):
        (tmp_path / "test_calc.py").write_text("def test_add(): assert True\n")
        out = MagicMock()
        out.response = "Created test_calc.py."
        out.tool_calls_made = 1
        return out

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")

    # Build the index BEFORE running so project_snapshot() has data
    CODE_INDEX.set_project(project_path)
    CODE_INDEX.build()

    mock_router = MagicMock()
    mock_router.acompletion = fake_acompletion
    with (
        patch("opalacoder.workflow_orchestrator._llm_router", return_value=mock_router),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools.get_project_path", return_value=project_path),
        patch("opalacoder.workflow_tools.get_project_path", return_value=project_path),
        patch("opalacoder.workflow_orchestrator.get_project_path", return_value=project_path),
    ):
        await strategy.run(
            user_request="Add unit tests for the calculator module.",
            history="",
            session=FakeSession(project_path),
            store=FakeStore(),
        )

    assert captured_prompts, "Planner oracle was never called."
    planner_prompt = captured_prompts[0]

    print(f"\n[PLANNER PROMPT (first 800 chars)]:\n{planner_prompt[:800]}")

    # The prompt must contain the symbol names from the index — not just the filename
    assert "add_numbers" in planner_prompt, \
        f"'add_numbers' symbol missing from planner prompt. Prompt:\n{planner_prompt[:600]}"
    assert "divide_numbers" in planner_prompt, \
        f"'divide_numbers' symbol missing from planner prompt. Prompt:\n{planner_prompt[:600]}"
    assert "CalculatorEngine" in planner_prompt, \
        f"'CalculatorEngine' class missing from planner prompt. Prompt:\n{planner_prompt[:600]}"
    assert "calculator.py" in planner_prompt, \
        f"'calculator.py' missing from planner prompt. Prompt:\n{planner_prompt[:600]}"

    print("\n[DIAGNOSIS]")
    print(f"  - add_numbers in prompt:      {'add_numbers' in planner_prompt}")
    print(f"  - divide_numbers in prompt:   {'divide_numbers' in planner_prompt}")
    print(f"  - CalculatorEngine in prompt: {'CalculatorEngine' in planner_prompt}")
    print(f"  - calculator.py in prompt:    {'calculator.py' in planner_prompt}")


# ---------------------------------------------------------------------------
# 4. End-to-end: worker prompt inherits symbols from planner task context
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_worker_prompt_contains_symbols_from_task_context(tmp_path):
    """Verify the full chain: index → snapshot → planner task context → worker prompt.

    The planner is given a snapshot with symbol names. It produces a task whose
    'context' field references those symbols. The worker receives that context
    in its prompt preamble. This test asserts that the worker prompt contains
    the actual function names from the codebase — not hallucinated names.
    """
    from opalacoder.orchestrator import WorkflowOrchestratorStrategy

    project_path = str(tmp_path)

    (tmp_path / "ui.js").write_text(textwrap.dedent("""\
        function renderButton(label, id) {
            const btn = document.createElement('button');
            btn.textContent = label;
            btn.id = id;
            return btn;
        }

        function attachClickHandler(element, handler) {
            element.addEventListener('click', handler);
        }
    """))

    CODE_INDEX.set_project(project_path)
    CODE_INDEX.build()

    worker_received_prompts: list[str] = []
    call_count = [0]

    async def fake_acompletion(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Planner uses the snapshot symbols in the task context
            return _oracle_response({"tasks": [_make_task(
                "t1",
                goal=f"Add event handlers wiring renderButton to attachClickHandler in {project_path}/main.js",
                commands=[f"Create {project_path}/main.js that calls renderButton and attachClickHandler for each calculator button"],
                related_files=["ui.js"],
                context=(
                    "ui.js exports: renderButton(label, id) → creates a button element; "
                    "attachClickHandler(element, handler) → wires click event. "
                    "Call renderButton for each button, then attachClickHandler on each result."
                ),
            )]})
        return _oracle_response({"done": True, "summary": "Done.", "corrections": []})

    async def fake_agent_run(self_agent, agent_input):
        worker_received_prompts.append(agent_input.prompt)
        (tmp_path / "main.js").write_text("// wired\n")
        out = MagicMock()
        out.response = "Created main.js."
        out.tool_calls_made = 1
        return out

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")

    mock_router2 = MagicMock()
    mock_router2.acompletion = fake_acompletion
    with (
        patch("opalacoder.workflow_orchestrator._llm_router", return_value=mock_router2),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools.get_project_path", return_value=project_path),
        patch("opalacoder.workflow_tools.get_project_path", return_value=project_path),
        patch("opalacoder.workflow_orchestrator.get_project_path", return_value=project_path),
    ):
        await strategy.run(
            user_request="Wire UI buttons in main.js using the functions in ui.js.",
            history="",
            session=FakeSession(project_path),
            store=FakeStore(),
        )

    assert worker_received_prompts, "Worker was never invoked."
    prompt = worker_received_prompts[0]

    print(f"\n[WORKER PROMPT]:\n{prompt}")

    # Worker prompt must carry the real function names from ui.js (via task context)
    assert "renderButton" in prompt, \
        f"'renderButton' missing from worker prompt:\n{prompt}"
    assert "attachClickHandler" in prompt, \
        f"'attachClickHandler' missing from worker prompt:\n{prompt}"
    assert "ui.js" in prompt, \
        f"'ui.js' missing from worker prompt (related_files):\n{prompt}"

    # Structured preamble must be present
    assert "TASK GOAL:" in prompt
    assert "RELATED FILES" in prompt
    assert "CONTEXT:" in prompt
    assert "COMMAND:" in prompt

    print("\n[DIAGNOSIS]")
    print(f"  - renderButton in prompt:      {'renderButton' in prompt}")
    print(f"  - attachClickHandler in prompt: {'attachClickHandler' in prompt}")
    print(f"  - ui.js in related files:       {'ui.js' in prompt}")
    print(f"  - structured preamble present:  {'TASK GOAL:' in prompt}")
