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
    from abcode.project import ProjectData
    return ProjectData(
        name=name,
        model=model,
        project_name=name,
        project_path="/tmp/test_proj",
        skills=["abcode"],
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
# NOTE: patch() objects must be recreated per test — a consumed context manager
# cannot be reused. So this is a factory function, not a module-level list.
def _common_patches():
    return [
        patch("abcode.planner.T.show_plan"),
        patch("abcode.planner.T.section"),
        patch("abcode.planner.T.success"),
        patch("abcode.planner.T.info"),
        patch("abcode.planner.T.thinking"),
        patch("abcode.planner.T.warning"),
        patch("pathlib.Path.write_text"),
    ]


# ---------------------------------------------------------------------------
# 1. refine_plan is called by run_pipeline
# ---------------------------------------------------------------------------

def test_run_pipeline_calls_refine_plan():
    """run_pipeline must invoke refine_plan (the plan refinement loop)."""
    project = _make_project()
    store = _make_store()
    mock_refine = AsyncMock(return_value="approved plan")

    with (
        patch("abcode.cli.get_relevant_skills_llm", new=AsyncMock(return_value="")),
        patch("abcode.planner.generate_panorama", new=AsyncMock(return_value="Phase 1: Do stuff")),
        patch("abcode.planner.refine_plan", new=mock_refine),
        patch("abcode.orchestrator.AutonomousOrchestratorStrategy.run", new=AsyncMock(return_value="Done")),
        patch("abcode.cli.T.section"),
        patch("abcode.cli.T.show_result"),
    ):
        from abcode.cli import run_pipeline
        _run(run_pipeline(
            project=project,
            store=store,
            max_retries=1,
            request="build a calculator",
            active_model="fake/model",
            project_skills=[],
        ))

    mock_refine.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Fast-path approval: plan returned unchanged
# ---------------------------------------------------------------------------

def test_refine_plan_fast_approval_returns_unchanged():
    """Typing 'sim' (a known approval word) must return the plan unchanged."""
    from abcode.planner import refine_plan

    original_plan = "Phase 1: Setup\nPhase 2: Build"
    project = _make_project()
    store = _make_store()

    with (
        patch("abcode.terminal.ask", return_value="sim"),
        patch("pathlib.Path.read_text", return_value=original_plan),
        *_common_patches(),
    ):
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
    from abcode.planner import refine_plan

    plan = "Phase 1: Something"
    project = _make_project()
    store = _make_store()

    with (
        patch("abcode.terminal.ask", return_value=""),
        patch("pathlib.Path.read_text", return_value=plan),
        *_common_patches(),
    ):
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
    from abcode.planner import refine_plan

    original_plan = "Phase 1: Setup"
    refined_plan  = "Phase 1: Setup\nPhase 2: Tests added"
    project = _make_project()
    store = _make_store()

    ask_seq = iter(["add tests please", "ok"])
    read_seq = iter([original_plan, refined_plan])

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(response=refined_plan))

    with (
        patch("abcode.terminal.ask", side_effect=lambda *a, **kw: next(ask_seq)),
        patch("pathlib.Path.read_text", side_effect=lambda *a, **kw: next(read_seq)),
        patch("abcode.planner.make_refinement_agent", return_value=mock_agent),
        patch("abcode.planner.confirm_plan", new=AsyncMock(return_value=MagicMock(approved=False))),
        patch("abcode.planner.T.spinner", new=_null_spinner),
        *_common_patches(),
    ):
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
    from abcode.planner import refine_plan
    from abcode.terminal import UserCancelled

    plan = "Phase 1: Something"
    project = _make_project()
    store = _make_store()

    with (
        patch("abcode.terminal.ask", side_effect=UserCancelled),
        patch("pathlib.Path.read_text", return_value=plan),
        *_common_patches(),
    ):
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

def test_run_pipeline_passes_correct_session_and_store():
    """run_pipeline must forward its project and store objects into refine_plan."""
    project = _make_project(name="my_proj")
    store = _make_store()
    captured = {}

    async def fake_refine(request, plan_text, model, session, store_arg):
        captured["session"] = session
        captured["store"] = store_arg
        return plan_text

    with (
        patch("abcode.cli.get_relevant_skills_llm", new=AsyncMock(return_value="")),
        patch("abcode.planner.generate_panorama", new=AsyncMock(return_value="Phase 1")),
        patch("abcode.planner.refine_plan", new=fake_refine),
        patch("abcode.orchestrator.AutonomousOrchestratorStrategy.run", new=AsyncMock(return_value="Done")),
        patch("abcode.cli.T.section"),
        patch("abcode.cli.T.show_result"),
    ):
        from abcode.cli import run_pipeline
        _run(run_pipeline(
            project=project,
            store=store,
            max_retries=1,
            request="do stuff",
            active_model="fake/model",
            project_skills=[],
        ))

    assert captured.get("session") is project, "refine_plan received wrong session object"
    assert captured.get("store") is store, "refine_plan received wrong store object"
