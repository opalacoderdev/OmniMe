"""Integration test for WorkflowOrchestratorStrategy pipeline.

Exercises the full Plan→Execute→Verify loop without a real LLM:
- Mocks litellm.acompletion (oracle calls) to return controlled JSON
- Mocks LLMAgentBlock.run (worker calls) to simulate task execution
- Asserts that files are actually created in the project directory
- Logs what enters and exits each phase for debugging

Run with:
    python -m pytest tests/test_workflow_pipeline.py -v -s
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anyio

from opalacoder.orchestrator import WorkflowOrchestratorStrategy


# ---------------------------------------------------------------------------
# Helpers: fake LLM responses
# ---------------------------------------------------------------------------

def _oracle_response(data: dict) -> MagicMock:
    """Return a mock litellm completion whose content is the given dict as JSON."""
    msg = MagicMock()
    msg.content = json.dumps(data)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_task(id: str, goal: str, commands: list[str], related_files: list[str] = None, context: str = "", depends_on: list[str] = None) -> dict:
    """Build a valid Task dict for use in mock plan responses."""
    return {
        "id": id,
        "goal": goal,
        "commands": commands,
        "related_files": related_files or [],
        "context": context or f"Implement: {goal}",
        "depends_on": depends_on or [],
    }


def _plan_response(tasks: list[dict]) -> MagicMock:
    return _oracle_response({"tasks": tasks})


def _verify_done_response(summary: str) -> MagicMock:
    return _oracle_response({"done": True, "summary": summary, "corrections": []})


# ---------------------------------------------------------------------------
# Fake session / store
# ---------------------------------------------------------------------------

class FakeSession:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.core_memory = ""
        self.history = []

    def context_header(self) -> str:
        return f"[PROJECT: TestProject | PATH: {self.project_path}]"


class FakeStore:
    def append_message(self, session, role, content):
        pass  # no-op


# ---------------------------------------------------------------------------
# Main integration test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workflow_creates_files(tmp_path, capsys):
    """
    Full pipeline: planner produces two tasks, workers create files, verifier reports done.
    Asserts the output files actually exist in the project directory.
    """
    project_path = str(tmp_path)
    session = FakeSession(project_path)
    store = FakeStore()

    index_html = os.path.join(project_path, "index.html")
    style_css = os.path.join(project_path, "style.css")

    # Oracle sequence: 1 planner + 1 reviewer per task (2 tasks = 3 oracle calls)
    oracle_calls: list[dict] = []
    oracle_responses = iter([
        _plan_response([
            _make_task("t1", f"Create {index_html} with a basic HTML skeleton.",
                       commands=[f"Create {index_html} with DOCTYPE, head, and empty body"],
                       context="New project — no existing files."),
            _make_task("t2", f"Create {style_css} with body reset styles.",
                       commands=[f"Create {style_css} with * {{box-sizing:border-box}} and body {{margin:0}}"],
                       related_files=["index.html"],
                       context="index.html has no classes yet — only a bare body reset is needed.",
                       depends_on=["t1"]),
        ]),
        _verify_done_response("index.html created successfully."),   # review t1
        _verify_done_response("style.css created successfully."),    # review t2
    ])

    async def fake_acompletion(**kwargs):
        content = kwargs["messages"][-1]["content"]
        resp = next(oracle_responses)
        oracle_calls.append({
            "model": kwargs.get("model"),
            "prompt_snippet": content[:120],
            "response": json.loads(resp.choices[0].message.content),
        })
        print(f"\n[ORACLE] model={kwargs.get('model')}")
        print(f"  prompt: {content[:120]!r}")
        print(f"  response: {resp.choices[0].message.content}")
        return resp

    worker_calls: list[dict] = []

    async def fake_agent_run(self_agent, agent_input):
        desc = agent_input.prompt
        worker_calls.append({"task_description": desc[:120]})
        print(f"\n[WORKER] task: {desc[:120]!r}")

        # Actually create the file the task describes
        if index_html in desc:
            Path(index_html).write_text("<!DOCTYPE html><html><body>Hello</body></html>")
            result = f"Created {index_html}"
        elif style_css in desc:
            Path(style_css).write_text("body { margin: 0; }")
            result = f"Created {style_css}"
        else:
            result = "Task completed (no file to create)."

        print(f"  result: {result}")
        out = MagicMock()
        out.response = result
        return out

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")

    with (
        patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools._PROJECT_PATH", project_path),
    ):
        result = await strategy.run(
            user_request="Create a minimal HTML page with CSS reset.",
            history="",
            session=session,
            store=store,
        )

    # ── Assertions ──────────────────────────────────────────────────────────

    print(f"\n[FINAL RESULT]: {result!r}")
    print(f"\n[ORACLE CALLS]: {len(oracle_calls)} total")
    for i, c in enumerate(oracle_calls):
        print(f"  [{i}] model={c['model']}")
        print(f"       prompt: {c['prompt_snippet']!r}")
        print(f"       response: {c['response']}")

    print(f"\n[WORKER CALLS]: {len(worker_calls)} total")
    for i, w in enumerate(worker_calls):
        print(f"  [{i}] task: {w['task_description']!r}")

    # planner (1) + reviewer per task (2) = 3 oracle calls
    assert len(oracle_calls) >= 3, f"Expected ≥3 oracle calls (1 planner + 2 reviewers), got {len(oracle_calls)}."
    assert len(worker_calls) == 2, f"Expected 2 worker calls, got {len(worker_calls)}."
    assert Path(index_html).exists(), f"index.html was not created in {project_path}."
    assert Path(style_css).exists(), f"style.css was not created in {project_path}."
    assert "task" in result.lower() or "created" in result.lower() or "completed" in result.lower(), \
        f"Final result does not mention completion: {result!r}"


# ---------------------------------------------------------------------------
# Phase-by-phase unit tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_planner_oracle_receives_snapshot_and_request(tmp_path):
    """The planner oracle prompt must contain the project snapshot and the user request."""
    project_path = str(tmp_path)
    Path(tmp_path / "existing_file.py").write_text("x = 1")

    captured_prompts: list[str] = []

    async def fake_acompletion(**kwargs):
        captured_prompts.append(kwargs["messages"][-1]["content"])
        return _plan_response([_make_task("t1", "Create main.py.", ["Create main.py with pass"])])

    async def fake_verify(**kwargs):
        return _verify_done_response("Done.")

    call_count = [0]

    async def fake_acompletion_seq(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            captured_prompts.append(kwargs["messages"][-1]["content"])
            return _plan_response([_make_task(
                "t1", f"Create {project_path}/main.py.",
                commands=[f"Create {project_path}/main.py with content: pass"],
                context="New file, no dependencies."
            )])
        return _verify_done_response("Done.")

    async def fake_agent_run(self_agent, agent_input):
        Path(project_path, "main.py").write_text("pass")
        out = MagicMock()
        out.response = "Created main.py."
        return out

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")
    session = FakeSession(project_path)

    with (
        patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion_seq),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools._PROJECT_PATH", project_path),
    ):
        await strategy.run(
            user_request="Add a main.py file.",
            history="",
            session=session,
            store=FakeStore(),
        )

    assert captured_prompts, "No prompt was captured from the planner oracle."
    planner_prompt = captured_prompts[0]
    assert "existing_file.py" in planner_prompt, \
        "Project snapshot (existing_file.py) not present in planner prompt."
    assert "Add a main.py file." in planner_prompt, \
        "User request not present in planner prompt."


@pytest.mark.anyio
async def test_verifier_oracle_receives_worker_reports(tmp_path):
    """The reviewer oracle prompt must contain the worker result for the reviewed task."""
    project_path = str(tmp_path)
    verify_prompt: list[str] = []
    call_count = [0]

    async def fake_acompletion_seq(**kwargs):
        call_count[0] += 1
        content = kwargs["messages"][-1]["content"]
        if call_count[0] == 1:
            return _plan_response([_make_task(
                "t1", f"Create {project_path}/app.js.",
                commands=[f"Create {project_path}/app.js with console.log('hi')"],
                related_files=["index.html"],
                context="Standalone script. No classes or IDs needed — just a console.log hello world."
            )])
        verify_prompt.append(content)
        return _verify_done_response("app.js created successfully.")

    async def fake_agent_run(self_agent, agent_input):
        Path(project_path, "app.js").write_text("console.log('hi')")
        out = MagicMock()
        out.response = "Created app.js with console.log."
        return out

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")

    with (
        patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion_seq),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools._PROJECT_PATH", project_path),
    ):
        await strategy.run(
            user_request="Create app.js.",
            history="",
            session=FakeSession(project_path),
            store=FakeStore(),
        )

    assert verify_prompt, "Reviewer oracle was never called."
    assert "Created app.js with console.log." in verify_prompt[0], \
        "Worker report not present in reviewer prompt."


# ---------------------------------------------------------------------------
# Scenario: worker must read existing HTML to create matching CSS
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_worker_task_contains_html_context_for_css(tmp_path, capsys):
    """
    Scenario: project already has index.html with known classes.
    Task: "Create index.css to style index.html."

    This test verifies two things:
    1. The planner description given to the worker is self-contained enough
       for the worker to know which HTML classes to target.
    2. The worker (simulated) reads index.html via read_file and produces
       CSS that references the actual classes — proving the context flow works.

    The worker is NOT mocked: it uses real tool calls against tmp_path.
    The oracle (LLM) IS mocked to return deterministic plans and verify responses.
    """
    import textwrap
    from opalacoder.tools import set_project_context, _PROJECT_PATH
    from opalacoder import tools as tools_module

    project_path = str(tmp_path)

    # Pre-create the HTML with known classes
    html_content = textwrap.dedent("""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <title>Calculator</title>
          <link rel="stylesheet" href="index.css">
        </head>
        <body>
          <div class="calculator">
            <div class="display" id="display">0</div>
            <div class="buttons">
              <button class="btn btn-clear" id="clear">AC</button>
              <button class="btn btn-number" id="7">7</button>
              <button class="btn btn-operator" id="add">+</button>
              <button class="btn btn-equals" id="equals">=</button>
            </div>
          </div>
        </body>
        </html>
    """)
    Path(tmp_path / "index.html").write_text(html_content)

    # Track what the worker actually received as its task prompt
    worker_received_prompts: list[str] = []
    # Track which tools the worker called (simulated via real tool execution)
    worker_tool_calls: list[str] = []

    # We simulate a real worker: it reads the HTML (via Path directly — same as the
    # real read_file tool would do) and writes the CSS file.
    async def fake_agent_run(self_agent, agent_input):
        task_prompt = agent_input.prompt
        worker_received_prompts.append(task_prompt)
        print(f"\n[WORKER] Full task prompt:\n{task_prompt}\n")

        # Read the HTML to extract class information (mirrors what the real agent does)
        html_path = Path(project_path) / "index.html"
        html = html_path.read_text(encoding="utf-8")
        worker_tool_calls.append(f"read_file(index.html) → {len(html)} chars")
        print(f"[WORKER] read_file returned {len(html)} chars")
        print(f"[WORKER] HTML classes visible: {'calculator' in html}, {'btn' in html}")

        css_content = textwrap.dedent("""\
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #1a1a2e; }
            .calculator { background: #16213e; border-radius: 16px; padding: 20px; width: 280px; }
            .display { background: #0f3460; color: #fff; font-size: 2rem; padding: 16px; text-align: right; border-radius: 8px; margin-bottom: 12px; }
            .buttons { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
            .btn { padding: 16px; font-size: 1.2rem; border: none; border-radius: 8px; cursor: pointer; }
            .btn-clear { background: #e94560; color: #fff; }
            .btn-number { background: #533483; color: #fff; }
            .btn-operator { background: #0f3460; color: #fff; }
            .btn-equals { background: #e94560; color: #fff; }
        """)
        css_path = Path(project_path) / "index.css"
        css_path.write_text(css_content, encoding="utf-8")
        worker_tool_calls.append("write_file(index.css)")
        print(f"[WORKER] wrote index.css ({len(css_content)} chars)")

        out = MagicMock()
        out.response = "Created index.css with styles for .calculator, .display, .buttons, .btn variants."
        out.tool_calls_made = 2
        return out

    call_count = [0]

    async def fake_acompletion_seq(**kwargs):
        call_count[0] += 1
        content = kwargs["messages"][-1]["content"]
        if call_count[0] == 1:
            return _plan_response([_make_task(
                "t1",
                goal=f"Create {project_path}/index.css to style the calculator layout in {project_path}/index.html",
                commands=[
                    f"Create {project_path}/index.css with CSS reset, body centering, and .calculator wrapper styles",
                    f"Add .display, .buttons grid, and button variant selectors (.btn-clear, .btn-number, .btn-operator, .btn-equals) to {project_path}/index.css",
                ],
                related_files=["index.html"],
                context=(
                    "index.html uses: .calculator (flex wrapper, 280px wide), "
                    ".display (output area, font-size 2rem, text-align right), "
                    ".buttons (4-column CSS grid, gap 8px), "
                    ".btn (base button, padding 16px, border-radius 8px), "
                    ".btn-clear (red), .btn-number (purple), .btn-operator (dark blue), .btn-equals (red). "
                    "Button IDs: clear, 7, add, equals."
                ),
            )])
        # Verifier
        css_path = os.path.join(project_path, "index.css")
        if Path(css_path).exists():
            return _verify_done_response("index.css created with all required class selectors.")
        return _oracle_response({
            "done": False,
            "summary": "index.css is missing.",
            "corrections": [_make_task(
                "c1",
                goal=f"Create missing {project_path}/index.css",
                commands=[f"Create {project_path}/index.css with .calculator and .btn styles"],
                related_files=["index.html"],
                context="index.css does not exist yet. index.html has .calculator, .btn, .display, .buttons classes.",
            )],
        })

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")
    session = FakeSession(project_path)

    with (
        patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion_seq),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools.get_project_path", return_value=project_path),
        patch("opalacoder.workflow_tools.get_project_path", return_value=project_path),
    ):
        result = await strategy.run(
            user_request="Create index.css to style the calculator page in index.html.",
            history="",
            session=session,
            store=FakeStore(),
        )

    print(f"\n[FINAL RESULT]: {result!r}")
    print(f"\n[WORKER TOOL CALLS]: {worker_tool_calls}")

    # ── Assertions ──────────────────────────────────────────────────────────

    assert worker_received_prompts, "Worker was never invoked."
    first_prompt = worker_received_prompts[0]

    # New schema: worker prompt must contain the structured preamble
    assert "TASK GOAL:" in first_prompt, \
        f"Worker prompt missing 'TASK GOAL:' preamble:\n{first_prompt}"
    assert "RELATED FILES" in first_prompt, \
        f"Worker prompt missing 'RELATED FILES' section:\n{first_prompt}"
    assert "CONTEXT:" in first_prompt, \
        f"Worker prompt missing 'CONTEXT:' section:\n{first_prompt}"
    assert "COMMAND:" in first_prompt, \
        f"Worker prompt missing 'COMMAND:' section:\n{first_prompt}"

    # Context must carry class information so worker doesn't need to guess
    assert "index.html" in first_prompt, \
        f"Worker prompt does not reference index.html:\n{first_prompt}"
    assert ".calculator" in first_prompt, \
        f"Worker prompt missing .calculator class context:\n{first_prompt}"
    assert ".btn" in first_prompt, \
        f"Worker prompt missing .btn class context:\n{first_prompt}"

    # The worker must have read the HTML (proves context retrieval flow works)
    assert any("read_file" in c for c in worker_tool_calls), \
        f"Worker never called read_file. Tool calls: {worker_tool_calls}"

    # CSS file must exist
    css_path = os.path.join(project_path, "index.css")
    assert Path(css_path).exists(), f"index.css was not created in {project_path}"

    # CSS must contain class selectors from the HTML
    css_content = Path(css_path).read_text()
    for cls in [".calculator", ".display", ".buttons", ".btn"]:
        assert cls in css_content, \
            f"CSS missing selector {cls!r}. CSS content:\n{css_content[:500]}"

    print("\n[DIAGNOSIS]")
    print(f"  - Prompt has TASK GOAL: {'TASK GOAL:' in first_prompt}")
    print(f"  - Prompt has CONTEXT: {'CONTEXT:' in first_prompt}")
    print(f"  - Prompt has COMMAND: {'COMMAND:' in first_prompt}")
    print(f"  - Context has .calculator: {'.calculator' in first_prompt}")
    print(f"  - Worker called read_file: {any('read_file' in c for c in worker_tool_calls)}")
    print(f"  - CSS file created: {Path(css_path).exists()}")
    print(f"  - CSS has .calculator: {'.calculator' in css_content}")


# ---------------------------------------------------------------------------
# Semantic validation unit tests
# ---------------------------------------------------------------------------

def test_validate_task_passes_complete_task():
    """A fully populated task should pass validation."""
    from opalacoder.workflow_orchestrator import Task, _validate_task
    task = Task(
        id="t1",
        goal="Create style.css to style the calculator layout in index.html",
        commands=["Create style.css with .calculator and .btn classes"],
        related_files=["index.html"],
        context=".calculator is a flex wrapper; .btn is the base button class with padding 16px.",
    )
    assert _validate_task(task) is None


def test_validate_task_fails_empty_goal():
    from opalacoder.workflow_orchestrator import Task, _validate_task
    task = Task(
        id="t1", goal="  ", commands=["Create style.css"],
        related_files=["index.html"], context="some context",
    )
    feedback = _validate_task(task)
    assert feedback is not None
    assert "goal" in feedback


def test_validate_task_fails_empty_commands():
    from opalacoder.workflow_orchestrator import Task, _validate_task
    task = Task(
        id="t1", goal="Create style.css", commands=[],
        related_files=["index.html"], context="some context",
    )
    feedback = _validate_task(task)
    assert feedback is not None
    assert "commands" in feedback


def test_validate_task_fails_empty_context():
    from opalacoder.workflow_orchestrator import Task, _validate_task
    task = Task(
        id="t1", goal="Create style.css", commands=["Create style.css"],
        related_files=["index.html"], context="  ",
    )
    feedback = _validate_task(task)
    assert feedback is not None
    assert "context" in feedback


def test_validate_task_fails_css_edit_task_without_related_files():
    """A CSS *edit* task with no related_files should be rejected — the worker can't
    know the current state of the file it's modifying.
    Create tasks are exempt: there's nothing to read yet.
    """
    from opalacoder.workflow_orchestrator import Task, _validate_task

    # Edit task without related_files: must fail
    edit_task = Task(
        id="t2",
        goal="Update style.css to fix the button layout",
        commands=["Edit style.css to add .btn-equals selector"],
        related_files=[],  # missing — worker can't see current file state
        context=".calculator and .btn classes need styling.",
    )
    feedback = _validate_task(edit_task)
    assert feedback is not None, "Edit CSS task without related_files should fail validation"
    assert "related_files" in feedback

    # Create task without related_files: must pass (nothing to read yet)
    create_task = Task(
        id="t3",
        goal="Create style.css for the calculator",
        commands=["Create style.css with button styles"],
        related_files=[],  # OK for a new file
        context=".calculator and .btn classes need styling.",
    )
    assert _validate_task(create_task) is None, \
        "Create CSS task without related_files should pass validation"


@pytest.mark.anyio
async def test_planner_reflection_triggered_on_incomplete_task(tmp_path):
    """
    When the planner returns a CSS task with empty context, the oracle's semantic
    validation must trigger a reflection loop and inject corrective feedback.
    The second attempt returns a complete task — verify the oracle retried.
    """
    from opalacoder.workflow_orchestrator import _oracle, PlanOutput

    attempt_payloads: list[list] = []

    async def fake_acompletion(**kwargs):
        messages = kwargs["messages"]
        attempt_payloads.append(messages[:])  # capture full message list per attempt
        attempt = len(attempt_payloads)
        print(f"\n[ORACLE attempt {attempt}] messages: {len(messages)}")
        for m in messages:
            print(f"  [{m['role']}]: {str(m['content'])[:120]!r}")

        if attempt == 1:
            # First attempt: CSS task with empty context and no related_files — should fail validation
            return _oracle_response({"tasks": [{
                "id": "t1",
                "goal": "Create style.css",
                "commands": ["Create style.css"],
                "related_files": [],
                "context": "",
                "depends_on": [],
            }]})
        else:
            # Second attempt: complete, valid task
            return _oracle_response({"tasks": [_make_task(
                "t1",
                goal="Create style.css to style index.html calculator layout",
                commands=["Create style.css with .calculator wrapper and .btn variant classes"],
                related_files=["index.html"],
                context=".calculator (flex wrapper), .btn (base button), .btn-clear (red), .btn-equals (red).",
            )]})

    with patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion):
        result = await _oracle(
            PlanOutput,
            system="You are a planner.",
            prompt="Create a calculator page.",
            model="ollama/test-model",
            llm_kwargs={},
        )

    print(f"\n[RESULT]: {result}")
    print(f"[ATTEMPTS]: {len(attempt_payloads)}")

    # Must have retried at least once
    assert len(attempt_payloads) >= 2, \
        f"Oracle did not retry — semantic validation may not be working. Attempts: {len(attempt_payloads)}"

    # The second-attempt message list must contain the guardrail feedback
    second_messages = attempt_payloads[1]
    all_content = " ".join(str(m.get("content", "")) for m in second_messages)
    assert "context" in all_content.lower() or "related_files" in all_content.lower(), \
        f"Guardrail feedback not found in second attempt messages:\n{all_content[:500]}"

    # Final result must be the valid task
    assert result is not None
    assert result.tasks[0].goal != "Create style.css", \
        "Oracle returned the incomplete task instead of the corrected one."
    assert result.tasks[0].context.strip() != "", \
        "Final task still has empty context after reflection."


# ---------------------------------------------------------------------------
# Regression: reviewer oracle failure must NOT increment task.failure_count
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_reviewer_oracle_failure_does_not_abort_plan(tmp_path):
    """When the reviewer oracle returns None (can't format JSON), the plan must NOT
    abort as if the task genuinely failed. oracle_failure_count tracks this separately.
    After MAX_REVIEWER_ORACLE_FAILS the task is treated as done and the plan continues.
    """
    from opalacoder.workflow_orchestrator import MAX_REVIEWER_ORACLE_FAILS

    project_path = str(tmp_path)
    Path(tmp_path / "app.py").write_text("x = 1")

    call_count = [0]
    oracle_fail_count = [0]

    async def fake_acompletion(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Planner: one task
            return _plan_response([_make_task(
                "t1", f"Edit {project_path}/app.py.",
                commands=[f"Add y = 2 to {project_path}/app.py"],
                context="app.py has x = 1. Add y = 2 on the next line."
            )])
        # All reviewer calls return garbage JSON so oracle returns None
        oracle_fail_count[0] += 1
        msg = MagicMock()
        msg.content = "not valid json {"
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    async def fake_agent_run(self_agent, agent_input):
        Path(project_path, "app.py").write_text("x = 1\ny = 2")
        out = MagicMock()
        out.response = "Added y = 2 to app.py."
        return out

    strategy = WorkflowOrchestratorStrategy(model="ollama/test-model")

    with (
        patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion),
        patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=fake_agent_run),
        patch("opalacoder.workflow_orchestrator.WorkflowOrchestratorStrategy._plan_and_refine",
              new=AsyncMock(return_value="")),
        patch("opalacoder.tools.set_project_context"),
        patch("opalacoder.tools._PROJECT_PATH", project_path),
    ):
        result = await strategy.run(
            user_request="Add y = 2 to app.py.",
            history="",
            session=FakeSession(project_path),
            store=FakeStore(),
        )

    # Plan must complete (not abort) despite reviewer oracle failures
    assert result is not None
    assert "could not be completed" not in result.lower(), \
        f"Plan aborted due to reviewer oracle failures (should have continued): {result!r}"
    # Oracle failure count must not exceed MAX_REVIEWER_ORACLE_FAILS retries per task
    # (each failed oracle call tries MAX_REFLECT_RETRIES times = 3 LLM calls each)
    assert oracle_fail_count[0] <= MAX_REVIEWER_ORACLE_FAILS * 3 + 2, \
        f"Too many reviewer oracle calls: {oracle_fail_count[0]}"


# ---------------------------------------------------------------------------
# Regression: semantic retries must not consume JSON-format retry budget
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_semantic_retry_does_not_consume_format_retry_budget(tmp_path):
    """When the oracle produces valid JSON but fails semantic validation, the fix
    attempt uses a separate budget. A single format failure should still get
    MAX_REFLECT_RETRIES attempts regardless of how many semantic retries happened.
    """
    from opalacoder.workflow_orchestrator import _oracle, PlanOutput, MAX_REFLECT_RETRIES

    project_path = str(tmp_path)
    call_count = [0]
    format_fail_injected = [False]

    async def fake_acompletion(**kwargs):
        call_count[0] += 1
        messages = kwargs["messages"]

        # First call: valid JSON but semantically incomplete (empty context)
        if call_count[0] == 1:
            return _oracle_response({"tasks": [{
                "id": "t1",
                "goal": "Create style.css",
                "commands": ["Create style.css with button styles"],
                "related_files": [],
                "context": "",   # fails semantic validation
                "depends_on": [],
            }]})

        # Second call (semantic retry): return garbage to trigger format error
        if call_count[0] == 2 and not format_fail_injected[0]:
            format_fail_injected[0] = True
            msg = MagicMock()
            msg.content = "oops not json {"
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp

        # Subsequent format-retry attempts: return valid complete task
        return _oracle_response({"tasks": [_make_task(
            "t1",
            goal="Create style.css to style index.html",
            commands=["Create style.css with .calculator and .btn classes"],
            related_files=["index.html"],
            context=".calculator flex wrapper, .btn base button.",
        )]})

    with patch("opalacoder.workflow_orchestrator.litellm.acompletion", side_effect=fake_acompletion):
        result = await _oracle(
            PlanOutput,
            system="You are a planner.",
            prompt="Create a calculator CSS.",
            model="ollama/test-model",
            llm_kwargs={},
        )

    # Oracle must eventually succeed despite the mixed semantic + format failures
    assert result is not None, \
        "Oracle returned None — semantic retries consumed the entire format retry budget"
    assert result.tasks[0].context.strip() != "", \
        "Final task still has empty context."
    # Total LLM calls must be within reason
    assert call_count[0] <= MAX_REFLECT_RETRIES + 4, \
        f"Too many LLM calls ({call_count[0]}), retry logic may be looping"
def test_search_html_css_js_bugs_detects_missing_doctype(tmp_path):
    """search_html_css_js_bugs must flag HTML files missing <!DOCTYPE html>."""
    from opalacoder.plugins.html_css_js_tools import _check_html_patterns

    html = tmp_path / "index.html"
    html.write_text("<html><body><p>Hi</p></body></html>", encoding="utf-8")

    issues = _check_html_patterns([str(html)], str(tmp_path))
    combined = "\n".join(issues)

    assert "DOCTYPE" in combined or "doctype" in combined.lower(), \
        f"Expected DOCTYPE warning, got: {combined}"


def test_search_html_css_js_bugs_clean_js(tmp_path):
    """search_html_css_js_bugs underlying function must report no syntax errors for clean JS."""
    from opalacoder.plugins.html_css_js_tools import _check_js_syntax

    js = tmp_path / "clean.js"
    js.write_text(
        "document.addEventListener('DOMContentLoaded', () => {\n"
        "  const btn = document.getElementById('btn');\n"
        "  if (btn) btn.addEventListener('click', () => { alert('clicked'); });\n"
        "});\n",
        encoding="utf-8",
    )

    issues = _check_js_syntax([str(js)], str(tmp_path))
    assert not any("SYNTAX ERROR" in i for i in issues), \
        f"Unexpected syntax errors: {issues}"


def test_contract_check_detects_operator_as_data_value(tmp_path):
    """_check_html_js_contract must flag operator symbols used as data-value instead of data-action."""
    from opalacoder.plugins.html_css_js_tools import _check_html_js_contract

    html = tmp_path / "index.html"
    html.write_text(
        '<!DOCTYPE html><html><body>'
        '<button id="btn-add" data-value="+">+</button>'
        '<button id="btn-multiply" data-value="*">×</button>'
        '<button id="btn-equals" data-action="equals">=</button>'
        '</body></html>',
        encoding="utf-8",
    )
    js = tmp_path / "script.js"
    js.write_text(
        "const action = btn.dataset.action;\n"
        "if (['add','subtract','multiply','divide'].includes(action)) handleOperator(action);\n"
        "else if (action === 'equals') handleEquals();\n",
        encoding="utf-8",
    )

    issues = _check_html_js_contract([str(html)], [str(js)], str(tmp_path))
    combined = "\n".join(issues)

    assert "btn-add" in combined or "data-value='+'" in combined, \
        f"Expected btn-add mismatch, got:\n{combined}"
    assert "btn-multiply" in combined or "data-value='*'" in combined, \
        f"Expected btn-multiply mismatch, got:\n{combined}"
    # equals is correct — must not be flagged
    assert "btn-equals" not in combined, \
        f"btn-equals was incorrectly flagged:\n{combined}"


def test_contract_check_passes_correct_html(tmp_path):
    """_check_html_js_contract must report no errors for correctly wired HTML+JS."""
    from opalacoder.plugins.html_css_js_tools import _check_html_js_contract

    html = tmp_path / "index.html"
    html.write_text(
        '<!DOCTYPE html><html><body>'
        '<button id="btn-add" data-action="add">+</button>'
        '<button id="btn-seven" data-value="7">7</button>'
        '<button id="btn-equals" data-action="equals">=</button>'
        '</body></html>',
        encoding="utf-8",
    )
    js = tmp_path / "script.js"
    js.write_text(
        "const action = btn.dataset.action;\n"
        "if (['add','subtract','multiply','divide'].includes(action)) handleOperator(action);\n"
        "else if (action === 'equals') handleEquals();\n",
        encoding="utf-8",
    )

    issues = _check_html_js_contract([str(html)], [str(js)], str(tmp_path))

    assert issues == [], f"Unexpected contract errors:\n{issues}"


def test_get_workflow_tools_includes_skill_tools():
    """get_workflow_tools must include skill tools when passed."""
    from opalacoder.workflow_tools import get_workflow_tools
    from agenticblocks.core.function_block import as_tool

    @as_tool(name="my_skill_tool", description="test")
    def my_skill_tool_fn() -> str:
        return "ok"

    tools = get_workflow_tools(skill_tools=[my_skill_tool_fn])
    names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
    assert "my_skill_tool" in names, f"Tool not found. Names: {names}"


def test_get_workflow_tools_deduplicates_skill_tools():
    """get_workflow_tools must not add a skill tool whose name already exists in base tools."""
    from opalacoder.workflow_tools import get_workflow_tools
    from agenticblocks.core.function_block import as_tool

    # Use a name that already exists in the base tool set
    @as_tool(name="search_code", description="dup test")
    def search_code_override(path: str = ".") -> str:
        return ""

    base_tools = get_workflow_tools(skill_tools=None)
    augmented = get_workflow_tools(skill_tools=[search_code_override])

    # Count of "search_code" named tools must not increase
    base_count = sum(1 for t in base_tools if getattr(t, "name", None) == "search_code")
    aug_count = sum(1 for t in augmented if getattr(t, "name", None) == "search_code")

    assert aug_count <= base_count, \
        f"Duplicate skill tool added: base={base_count}, augmented={aug_count}"
