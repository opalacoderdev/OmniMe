"""Integration tests for the deterministic workflow pipeline.

These tests exercise execute_subplans() end-to-end with a mocked LLM/executor so
we can verify:
  - what task prompt each subplan receives
  - that the context passed to SP-N reflects what SP-(N-1) actually wrote
  - that all files land inside a single project directory, never in the project root
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorOutput

from abcode.executor import execute_subplans
from abcode.subplan import Subplan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sp(sp_id: str, objective: str, steps: list[str] | None = None) -> Subplan:
    return Subplan(
        id=sp_id,
        phase="test",
        objective=objective,
        prerequisites=[],
        steps=steps or ["step"],
        completion_criterion="done",
    )


def _ok_result(code: str = "", stdout: str = "done") -> CodePlanExecutorOutput:
    return CodePlanExecutorOutput(
        response="ok",
        code_generated=code,
        execution_stdout=stdout,
        execution_stderr="",
        success=True,
    )


class FakeExecutorBlock:
    """Simulates CodePlanExecutorBlock.

    Each call records the task prompt and executes the provided Python code
    in the current working directory (already set to project_dir by
    SubplanExecutionBlock before calling us).
    """

    def __init__(self, code_per_call: list[str]):
        self._codes = list(code_per_call)
        self.recorded_tasks: list[str] = []

    async def run(self, inp):
        self.recorded_tasks.append(inp.task)
        code = self._codes.pop(0) if self._codes else ""
        if code:
            exec(compile(code, "<test>", "exec"), {})
        return _ok_result(code=code)


def _run(coro):
    """Run a coroutine synchronously — avoids pytest-asyncio configuration."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_files_created_in_project_subdir():
    """All files must end up inside the project subdirectory, not in the CWD root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            sp1_code = "from pathlib import Path; Path('index.html').write_text('<html/>')"
            sp2_code = "from pathlib import Path; Path('style.css').write_text('body{}')"
            fake_executor = FakeExecutorBlock([sp1_code, sp2_code])

            with patch("abcode.executor.make_executor_block", return_value=fake_executor), \
                 patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")):
                _run(execute_subplans(
                    subplans=[_sp("SP-1", "Create HTML"), _sp("SP-2", "Create CSS")],
                    original_request="create a calculator app",
                    model="fake-model",
                ))

            root_files = [p.name for p in Path(tmpdir).iterdir() if p.is_file()]
            assert root_files == [], f"Files found in project root: {root_files}"

            subdirs = [p for p in Path(tmpdir).iterdir() if p.is_dir()]
            assert len(subdirs) == 1, f"Expected exactly 1 subdir, got: {subdirs}"

            created = {p.name for p in subdirs[0].rglob("*") if p.is_file()}
            assert "index.html" in created
            assert "style.css" in created
        finally:
            os.chdir(original_cwd)


def test_sp2_task_prompt_lists_files_from_sp1():
    """SP-2's task prompt must include the files created by SP-1.

    This verifies that context comes from the real filesystem, not LLM stdout parsing
    (which was the source of the 'PROJECT_DIR: the' bug).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            sp1_code = "from pathlib import Path; Path('index.html').write_text('<html/>')"
            fake_executor = FakeExecutorBlock([sp1_code, ""])

            with patch("abcode.executor.make_executor_block", return_value=fake_executor), \
                 patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")):
                _run(execute_subplans(
                    subplans=[_sp("SP-1", "Create HTML"), _sp("SP-2", "Add CSS")],
                    original_request="create a calculator app",
                    model="fake-model",
                ))

            assert len(fake_executor.recorded_tasks) == 2
            sp2_prompt = fake_executor.recorded_tasks[1]

            assert "index.html" in sp2_prompt, (
                f"SP-2 prompt does not mention 'index.html' — context not propagated.\n\n"
                f"SP-2 context section:\n{sp2_prompt}"
            )
            assert "DO NOT recreate" in sp2_prompt or "already present" in sp2_prompt, (
                "SP-2 prompt does not warn the LLM against recreating existing files."
            )
        finally:
            os.chdir(original_cwd)


def test_context_not_corrupted_by_stdout_parsing():
    """SP-2 context must NOT contain garbage like 'PROJECT_DIR: the'.

    Regression test: _extract_context_regex previously matched 'the' from
    'Created the following files:' as the project directory name.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            sp1_code = (
                "from pathlib import Path\n"
                "Path('index.html').write_text('<html/>')\n"
                "print('Created the following files:')\n"
                "print('index.html')\n"
            )
            fake_executor = FakeExecutorBlock([sp1_code, ""])

            with patch("abcode.executor.make_executor_block", return_value=fake_executor), \
                 patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")):
                _run(execute_subplans(
                    subplans=[_sp("SP-1", "Create HTML"), _sp("SP-2", "Add CSS")],
                    original_request="create a calculator app",
                    model="fake-model",
                ))

            sp2_prompt = fake_executor.recorded_tasks[1]
            assert "PROJECT_DIR: the" not in sp2_prompt, (
                "Regression: 'PROJECT_DIR: the' in SP-2 prompt — stdout still being parsed."
            )
        finally:
            os.chdir(original_cwd)


def test_each_subplan_runs_in_same_project_directory():
    """Every subplan must write files to the same project subdirectory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            def make_code(filename: str) -> str:
                return (
                    "from pathlib import Path\n"
                    f"Path('{filename}').write_text('x')\n"
                )

            fake_executor = FakeExecutorBlock([
                make_code("index.html"),
                make_code("style.css"),
                make_code("script.js"),
            ])

            with patch("abcode.executor.make_executor_block", return_value=fake_executor), \
                 patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")):
                _run(execute_subplans(
                    subplans=[
                        _sp("SP-1", "Create HTML"),
                        _sp("SP-2", "Create CSS"),
                        _sp("SP-3", "Create JS"),
                    ],
                    original_request="create a calculator app",
                    model="fake-model",
                ))

            all_files = list(Path(tmpdir).rglob("*.html")) + \
                        list(Path(tmpdir).rglob("*.css")) + \
                        list(Path(tmpdir).rglob("*.js"))

            parent_dirs = {f.parent for f in all_files}
            assert len(parent_dirs) == 1, (
                f"Files scattered across multiple directories: {parent_dirs}\n"
                f"All files: {all_files}"
            )
            assert parent_dirs.pop() != Path(tmpdir), (
                "Files landed in the project root instead of a named subdirectory."
            )
        finally:
            os.chdir(original_cwd)
