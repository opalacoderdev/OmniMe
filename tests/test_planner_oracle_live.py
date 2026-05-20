"""Live planner oracle test — calls the real LLM (no mocks).

This test exercises the full _oracle(PlanOutput) call against the configured
model (Ollama by default) and inspects the generated plan JSON field by field.

Purpose:
  - Observe what the LLM actually produces for a concrete request
  - Detect regressions in task schema completeness (goal/commands/context quality)
  - Surface semantic validation feedback cycles (how many retries the oracle needs)
  - Diagnose whether the model fills context with real class/ID names or leaves it vague

Usage:
    python -m pytest tests/test_planner_oracle_live.py -v -s
    python -m pytest tests/test_planner_oracle_live.py -v -s -k "calculator"

Skipped automatically if Ollama is not reachable.
"""

import json
import textwrap
from pathlib import Path

import pytest

# Import orchestrator first so the circular import between orchestrator.py and
# workflow_orchestrator.py is resolved before any test imports workflow_orchestrator
# internals directly.
from opalacoder.orchestrator import WorkflowOrchestratorStrategy  # noqa: F401
import opalacoder.workflow_orchestrator as _wf_mod

_oracle = _wf_mod._oracle
_project_snapshot = _wf_mod._project_snapshot
_validate_task = _wf_mod._validate_task
PlanOutput = _wf_mod.PlanOutput

# ---------------------------------------------------------------------------
# Skip marker — skip entire module if Ollama is unreachable
# ---------------------------------------------------------------------------

def _ollama_available() -> bool:
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama not reachable at localhost:11434 — skipping live LLM tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_plan(plan) -> None:
    print(f"\n{'='*60}")
    print(f"  PLAN — {len(plan.tasks)} task(s)")
    print('='*60)
    for task in plan.tasks:
        print(f"\n  [{task.id}] GOAL: {task.goal}")
        print(f"       depends_on: {task.depends_on}")
        print(f"       related_files: {task.related_files}")
        print(f"       commands ({len(task.commands)}):")
        for i, cmd in enumerate(task.commands, 1):
            print(f"         {i}. {cmd}")
        print(f"       context ({len(task.context)} chars):")
        # Print context indented, wrapping long lines
        for line in textwrap.wrap(task.context, width=70):
            print(f"         {line}")
    print('='*60)


def _score_task(task) -> dict:
    """Return a quality score dict for a single task."""

    return {
        "id": task.id,
        "has_goal": bool(task.goal.strip()),
        "has_commands": len(task.commands) > 0,
        "num_commands": len(task.commands),
        "has_context": bool(task.context.strip()),
        "context_len": len(task.context),
        "has_related_files": len(task.related_files) > 0,
        "depends_on": task.depends_on,
        "validation_error": _validate_task(task),
    }


# ---------------------------------------------------------------------------
# Fixtures: synthetic projects
# ---------------------------------------------------------------------------

@pytest.fixture()
def calculator_project(tmp_path: Path) -> Path:
    """A minimal calculator project: index.html + empty script.js placeholder."""
    (tmp_path / "index.html").write_text(textwrap.dedent("""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <title>Calculator</title>
          <link rel="stylesheet" href="style.css">
          <script src="script.js" defer></script>
        </head>
        <body>
          <div class="calculator">
            <div class="display" id="display">0</div>
            <div class="buttons">
              <button class="btn btn-clear" id="clear">AC</button>
              <button class="btn btn-delete" id="delete">DEL</button>
              <button class="btn btn-operator" id="divide">/</button>
              <button class="btn btn-operator" id="multiply">*</button>
              <button class="btn btn-number" id="7">7</button>
              <button class="btn btn-number" id="8">8</button>
              <button class="btn btn-number" id="9">9</button>
              <button class="btn btn-operator" id="subtract">-</button>
              <button class="btn btn-number" id="4">4</button>
              <button class="btn btn-number" id="5">5</button>
              <button class="btn btn-number" id="6">6</button>
              <button class="btn btn-operator" id="add">+</button>
              <button class="btn btn-number" id="1">1</button>
              <button class="btn btn-number" id="2">2</button>
              <button class="btn btn-number" id="3">3</button>
              <button class="btn btn-equals" id="equals">=</button>
              <button class="btn btn-number btn-zero" id="0">0</button>
              <button class="btn btn-decimal" id="decimal">.</button>
            </div>
          </div>
        </body>
        </html>
    """))
    return tmp_path


@pytest.fixture()
def python_api_project(tmp_path: Path) -> Path:
    """A Python project with an existing auth module and missing tests."""
    (tmp_path / "auth.py").write_text(textwrap.dedent("""\
        import hashlib
        import secrets

        def hash_password(password: str) -> str:
            salt = secrets.token_hex(16)
            hashed = hashlib.sha256((salt + password).encode()).hexdigest()
            return f"{salt}:{hashed}"

        def verify_password(password: str, stored_hash: str) -> bool:
            salt, hashed = stored_hash.split(":", 1)
            return hashlib.sha256((salt + password).encode()).hexdigest() == hashed

        def generate_token(user_id: int) -> str:
            return secrets.token_urlsafe(32)
    """))
    return tmp_path


# ---------------------------------------------------------------------------
# Live tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_planner_generates_valid_schema_for_calculator_css(calculator_project, capsys):
    """
    Request: create style.css for the calculator HTML.
    Expected: planner produces at least one task with non-empty context
    that mentions CSS class names from index.html.
    """
    from opalacoder.config import get_agent_llm_kwargs
    from opalacoder.code_index import CODE_INDEX
    import opalacoder.tools as tools_module

    project_path = str(calculator_project)

    CODE_INDEX.set_project(project_path)
    CODE_INDEX.build()

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(tools_module, "_PROJECT_PATH", project_path)

        strategy = WorkflowOrchestratorStrategy()
        session_mock = type("S", (), {
            "project_path": project_path,
            "core_memory": "",
        })()
        project_context = f"[PROJECT: Calculator | PATH: {project_path}]"
        planner_sys = strategy._planner_system(project_context, session_mock)
        llm_kwargs = get_agent_llm_kwargs("orchestrator")

        snapshot = _project_snapshot()
        planning_prompt = (
            f"Project files:\n{snapshot}\n\n"
            f"User request:\nCreate style.css to style the calculator page defined in index.html."
        )

        print(f"\n[SYSTEM PROMPT] (first 600 chars):\n{planner_sys[:600]}\n")
        print(f"[PLANNING PROMPT] (first 400 chars):\n{planning_prompt[:400]}\n")

        plan = await _oracle(
            PlanOutput,
            planner_sys,
            planning_prompt,
            model=strategy.model,
            llm_kwargs=llm_kwargs,
        )

    print(f"\n[RAW RESULT]: plan={'None (oracle failed)' if plan is None else 'OK'}")
    assert plan is not None, "Oracle returned None — model failed to produce valid JSON after all retries."

    _print_plan(plan)

    scores = [_score_task(t) for t in plan.tasks]
    print("\n[QUALITY SCORES]:")
    for s in scores:
        validation = s["validation_error"] or "OK"
        print(f"  {s['id']}: goal={s['has_goal']} commands={s['num_commands']} "
              f"context_len={s['context_len']} related_files={s['has_related_files']} "
              f"validation={validation}")

    # --- Assertions ---

    assert len(plan.tasks) >= 1, "Planner produced zero tasks."

    # Every task must pass semantic validation
    failed = [s for s in scores if s["validation_error"]]
    assert not failed, (
        f"Semantic validation failed for {len(failed)} task(s):\n"
        + "\n".join(f"  {s['id']}: {s['validation_error']}" for s in failed)
    )

    # At least one task must target style.css
    css_tasks = [t for t in plan.tasks if "style.css" in t.goal or
                 any("style.css" in c for c in t.commands)]
    assert css_tasks, (
        f"No task targets style.css. Goals:\n"
        + "\n".join(f"  {t.id}: {t.goal}" for t in plan.tasks)
    )

    # The CSS task must have non-trivial context (class names from the HTML)
    css_task = css_tasks[0]
    html_classes = [".calculator", ".display", ".buttons", ".btn"]
    found_classes = [cls for cls in html_classes if cls in css_task.context]
    print(f"\n[CSS TASK CONTEXT QUALITY]: found {len(found_classes)}/{len(html_classes)} expected classes")
    print(f"  found: {found_classes}")
    print(f"  missing: {[c for c in html_classes if c not in css_task.context]}")

    assert len(found_classes) >= 2, (
        f"CSS task context is too vague — only {len(found_classes)} HTML class(es) mentioned.\n"
        f"Context was:\n{css_task.context}"
    )


@pytest.mark.anyio
async def test_planner_generates_valid_schema_for_python_tests(python_api_project, capsys):
    """
    Request: write unit tests for auth.py.
    Expected: planner produces tasks with function signatures in context
    and test_auth.py in commands.
    """
    from opalacoder.config import get_agent_llm_kwargs
    from opalacoder.code_index import CODE_INDEX
    import opalacoder.tools as tools_module

    project_path = str(python_api_project)

    CODE_INDEX.set_project(project_path)
    CODE_INDEX.build()

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(tools_module, "_PROJECT_PATH", project_path)

        strategy = WorkflowOrchestratorStrategy()
        session_mock = type("S", (), {
            "project_path": project_path,
            "core_memory": "",
        })()
        project_context = f"[PROJECT: Auth | PATH: {project_path}]"
        planner_sys = strategy._planner_system(project_context, session_mock)
        llm_kwargs = get_agent_llm_kwargs("orchestrator")

        snapshot = _project_snapshot()
        planning_prompt = (
            f"Project files:\n{snapshot}\n\n"
            f"User request:\nWrite unit tests for auth.py covering hash_password, "
            f"verify_password, and generate_token."
        )

        print(f"\n[SNAPSHOT]:\n{snapshot}\n")

        plan = await _oracle(
            PlanOutput,
            planner_sys,
            planning_prompt,
            model=strategy.model,
            llm_kwargs=llm_kwargs,
        )

    assert plan is not None, "Oracle returned None after all retries."

    _print_plan(plan)

    scores = [_score_task(t) for t in plan.tasks]
    print("\n[QUALITY SCORES]:")
    for s in scores:
        print(f"  {s['id']}: goal={s['has_goal']} commands={s['num_commands']} "
              f"context_len={s['context_len']} validation={s['validation_error'] or 'OK'}")

    # Every task must pass semantic validation
    failed = [s for s in scores if s["validation_error"]]
    assert not failed, (
        f"Semantic validation failed:\n"
        + "\n".join(f"  {s['id']}: {s['validation_error']}" for s in failed)
    )

    # At least one task must mention test_auth.py or the functions
    all_text = " ".join(t.goal + " ".join(t.commands) + t.context for t in plan.tasks)
    assert "auth" in all_text.lower(), "Plan makes no reference to auth module."

    # Context must carry function signatures
    known_fns = ["hash_password", "verify_password", "generate_token"]
    found_fns = [fn for fn in known_fns if fn in all_text]
    print(f"\n[FUNCTION COVERAGE]: {len(found_fns)}/{len(known_fns)} functions mentioned")
    print(f"  found: {found_fns}")
    print(f"  missing: {[f for f in known_fns if f not in all_text]}")

    assert len(found_fns) >= 2, (
        f"Plan context only mentions {len(found_fns)} function(s) — too vague to write correct tests.\n"
        f"Expected at least: hash_password, verify_password"
    )


@pytest.mark.anyio
async def test_planner_retries_on_incomplete_context(tmp_path, capsys):
    """
    Observe the reflection loop in action: intercept oracle calls to count
    how many attempts were needed when the model returns incomplete context.

    This test does NOT mock — it calls the real LLM. It passes regardless of
    how many retries occurred, but prints the retry count for diagnosis.
    The purpose is to make the retry behavior observable in CI logs.
    """
    from opalacoder.config import get_agent_llm_kwargs
    from opalacoder.code_index import CODE_INDEX
    import litellm
    import opalacoder.tools as tools_module

    project_path = str(tmp_path)
    (tmp_path / "widget.py").write_text("def render_widget(size: int, color: str) -> str:\n    pass\n")

    CODE_INDEX.set_project(project_path)
    CODE_INDEX.build()

    attempt_log: list[dict] = []
    _original_acompletion = litellm.acompletion

    async def instrumented_acompletion(**kwargs):
        messages = kwargs.get("messages", [])
        attempt_log.append({
            "num_messages": len(messages),
            "last_role": messages[-1]["role"] if messages else "?",
            "is_retry": any("[GUARDRAIL" in str(m.get("content", "")) for m in messages),
        })
        return await _original_acompletion(**kwargs)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(tools_module, "_PROJECT_PATH", project_path)
        mp.setattr(litellm, "acompletion", instrumented_acompletion)

        strategy = WorkflowOrchestratorStrategy()
        session_mock = type("S", (), {"project_path": project_path, "core_memory": ""})()
        planner_sys = strategy._planner_system(
            f"[PROJECT: Widget | PATH: {project_path}]", session_mock
        )
        llm_kwargs = get_agent_llm_kwargs("orchestrator")

        plan = await _oracle(
            PlanOutput,
            planner_sys,
            f"Project files:\nwidget.py [function render_widget]\n\n"
            f"User request:\nAdd a Python unit test for render_widget in test_widget.py.",
            model=strategy.model,
            llm_kwargs=llm_kwargs,
        )

    print(f"\n[ATTEMPT LOG] ({len(attempt_log)} total oracle call(s)):")
    for i, a in enumerate(attempt_log, 1):
        print(f"  attempt {i}: messages={a['num_messages']} is_retry={a['is_retry']}")

    if plan:
        _print_plan(plan)
        scores = [_score_task(t) for t in plan.tasks]
        retries = sum(1 for a in attempt_log if a["is_retry"])
        print(f"\n[SUMMARY]")
        print(f"  Total LLM calls: {len(attempt_log)}")
        print(f"  Reflection retries triggered: {retries}")
        print(f"  Final plan tasks: {len(plan.tasks)}")
        print(f"  All tasks valid: {all(s['validation_error'] is None for s in scores)}")
    else:
        print("\n[SUMMARY] Oracle failed after all retries — plan is None.")

    # This test always passes — its purpose is to make retry behavior visible.
    # If the oracle returns None after retries, that itself is useful signal.
    assert True
