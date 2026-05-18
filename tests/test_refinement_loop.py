"""Tests for the plan refinement loop (planner.refine_plan).

Verifies that:
1. refine_plan is actually called by run_pipeline
2. Immediate approval (fast-path) returns the plan unchanged
3. Empty Enter approves immediately
4. A feedback cycle correctly refines the plan and the LLM is called
5. Cancellation (UserCancelled) propagates correctly
6. refine_plan receives the correct session/store objects from run_pipeline
"""

import asyncio
import contextlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_project(name="test_proj", model="fake/model"):
    from opalacoder.project import ProjectData
    return ProjectData(
        name=name,
        model=model,
        project_name=name,
        project_path="/tmp/test_proj",
        skills=["opalacoder"],
    )


def _make_store():
    store = MagicMock()
    store.append_message = MagicMock()
    store.save = MagicMock()
    return store


@contextlib.contextmanager
def _null_spinner(*args, **kwargs):
    """Replacement for terminal.spinner that does nothing."""
    yield MagicMock()


# Common patches for tests that call refine_plan directly.
def _common_patches():
    return [
        patch("opalacoder.planner.T.show_plan"),
        patch("opalacoder.planner.T.section"),
        patch("opalacoder.planner.T.success"),
        patch("opalacoder.planner.T.info"),
        patch("opalacoder.planner.T.thinking"),
        patch("opalacoder.planner.T.warning"),
        patch("pathlib.Path.write_text"),
    ]


# ---------------------------------------------------------------------------
# 1. refine_plan is called by run_pipeline
# ---------------------------------------------------------------------------

def test_orchestrator_calls_refine_plan():
    """_plan_and_refine must invoke refine_plan (the plan refinement loop)."""
    project = _make_project()
    store = _make_store()
    mock_refine = AsyncMock(return_value="approved plan")

    with (
        patch("opalacoder.planner.generate_panorama", new=AsyncMock(return_value="Phase 1: Do stuff")),
        patch("opalacoder.planner.refine_plan", new=mock_refine),
        patch("opalacoder.orchestrator.T.section"),
        patch("builtins.open", MagicMock()),
        patch("os.makedirs", MagicMock()),
    ):
        from opalacoder.orchestrator import AutonomousOrchestratorStrategy
        strategy = AutonomousOrchestratorStrategy(model="fake/model")
        _run(strategy._plan_and_refine("build a calculator", "", project, store))

    mock_refine.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Fast-path approval: plan returned unchanged
# ---------------------------------------------------------------------------

def test_refine_plan_fast_approval_returns_unchanged():
    """Typing 'sim' (a known approval word) must return the plan unchanged."""
    from opalacoder.planner import refine_plan

    original_plan = "Phase 1: Setup\nPhase 2: Build"
    project = _make_project()
    store = _make_store()

    patches = [
        patch("opalacoder.terminal.ask", return_value="sim"),
        patch("pathlib.Path.read_text", return_value=original_plan),
    ] + _common_patches()

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = _run(refine_plan(
            request="build something",
            plan_text=original_plan,
            model="fake/model",
            session=project,
            store=store,
        ))

    assert result == original_plan
    store.append_message.assert_any_call(project, "assistant", original_plan)
    store.append_message.assert_any_call(project, "user", "sim")


# ---------------------------------------------------------------------------
# 3. Empty Enter = fast approval
# ---------------------------------------------------------------------------

def test_refine_plan_empty_enter_approves():
    """Pressing Enter (empty input) must approve the plan immediately."""
    from opalacoder.planner import refine_plan

    plan = "Phase 1: Something"
    project = _make_project()
    store = _make_store()

    patches = [
        patch("opalacoder.terminal.ask", return_value=""),
        patch("pathlib.Path.read_text", return_value=plan),
    ] + _common_patches()

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = _run(refine_plan(
            request="build something",
            plan_text=plan,
            model="fake/model",
            session=project,
            store=store,
        ))

    assert result == plan


# ---------------------------------------------------------------------------
# 4. One refinement cycle: feedback → LLM refines → user approves
# ---------------------------------------------------------------------------

def test_refine_plan_one_cycle_then_approve():
    """One round of feedback must call the refinement LLM, then approve on 'ok'."""
    from opalacoder.planner import refine_plan

    original_plan = "Phase 1: Setup"
    refined_plan  = "Phase 1: Setup\nPhase 2: Tests added"
    project = _make_project()
    store = _make_store()

    ask_seq = iter(["add tests please", "ok"])
    read_seq = iter([original_plan, refined_plan])

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(response=refined_plan))

    patches = [
        patch("opalacoder.terminal.ask", side_effect=lambda *a, **kw: next(ask_seq)),
        patch("pathlib.Path.read_text", side_effect=lambda *a, **kw: next(read_seq)),
        patch("opalacoder.planner.make_refinement_agent", return_value=mock_agent),
        patch("opalacoder.planner.confirm_plan", new=AsyncMock(return_value=MagicMock(approved=False))),
        patch("opalacoder.planner.T.spinner", new=_null_spinner),
    ] + _common_patches()

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = _run(refine_plan(
            request="build something",
            plan_text=original_plan,
            model="fake/model",
            session=project,
            store=store,
        ))

    assert result == refined_plan
    mock_agent.run.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Cancellation propagates UserCancelled
# ---------------------------------------------------------------------------

def test_refine_plan_cancel_raises():
    """Calling terminal.ask with /cancel must bubble UserCancelled out."""
    from opalacoder.planner import refine_plan
    from opalacoder.terminal import UserCancelled

    plan = "Phase 1: Something"
    project = _make_project()
    store = _make_store()

    patches = [
        patch("opalacoder.terminal.ask", side_effect=UserCancelled),
        patch("pathlib.Path.read_text", return_value=plan),
    ] + _common_patches()

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with pytest.raises(UserCancelled):
            _run(refine_plan(
                request="build something",
                plan_text=plan,
                model="fake/model",
                session=project,
                store=store,
            ))


# ---------------------------------------------------------------------------
# 6. run_pipeline forwards the real project and store to refine_plan
# ---------------------------------------------------------------------------

def test_orchestrator_passes_correct_session_and_store():
    """_plan_and_refine must forward its project and store objects into refine_plan."""
    project = _make_project(name="my_proj")
    store = _make_store()
    captured = {}

    async def fake_refine(request, plan_text, model, session, store_arg):
        captured["session"] = session
        captured["store"] = store_arg
        return plan_text

    with (
        patch("opalacoder.planner.generate_panorama", new=AsyncMock(return_value="Phase 1")),
        patch("opalacoder.planner.refine_plan", new=fake_refine),
        patch("opalacoder.orchestrator.T.section"),
        patch("builtins.open", MagicMock()),
        patch("os.makedirs", MagicMock()),
    ):
        from opalacoder.orchestrator import AutonomousOrchestratorStrategy
        strategy = AutonomousOrchestratorStrategy(model="fake/model")
        _run(strategy._plan_and_refine("do stuff", "", project, store))

    assert captured.get("session") is project, "refine_plan received wrong session object"
    assert captured.get("store") is store, "refine_plan received wrong store object"
