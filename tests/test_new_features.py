"""Tests for features added after the initial implementation:

1. user_request_for_dir: execute_subplans() must use the raw user request
   (not a context-prefixed string) to derive the project directory name.

2. Timeout (60 s): SubplanExecutionBlock must cancel code that hangs and
   record a meaningful error instead of freezing indefinitely.

3. Banned server commands: the task prompt must explicitly forbid
   python -m http.server and other long-running processes.
"""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorOutput

from abcode.executor import (
    _build_task,
    _infer_project_dir_from_request,
    execute_subplans,
)
from abcode.subplan import Subplan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sp(sp_id: str, objective: str = "do something") -> Subplan:
    return Subplan(
        id=sp_id,
        phase="test",
        objective=objective,
        prerequisites=[],
        steps=["step 1"],
        completion_criterion="done",
    )


def _ok_result(stdout: str = "done") -> CodePlanExecutorOutput:
    return CodePlanExecutorOutput(
        response="ok",
        code_generated="",
        execution_stdout=stdout,
        execution_stderr="",
        success=True,
    )


class FakeExecutorBlock:
    def __init__(self, result: CodePlanExecutorOutput):
        self._result = result
        self.recorded_tasks: list[str] = []

    async def run(self, inp):
        self.recorded_tasks.append(inp.task)
        return self._result


class HangingExecutorBlock:
    """Simulates an executor that never returns (server started, infinite loop, etc.)"""
    async def run(self, inp):
        await asyncio.sleep(9999)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. user_request_for_dir
# ---------------------------------------------------------------------------

class TestUserRequestForDir:
    def test_plain_request_gives_correct_dir(self):
        """When user_request_for_dir is a clean user request, the dir name is derived from it."""
        result = _infer_project_dir_from_request("quero criar um app de calculadora")
        assert result == "app-de-calculadora"

    def test_context_prefixed_request_gives_wrong_dir(self):
        """Without user_request_for_dir, passing a context-prefixed string that contains no
        matching verb produces a bad (fallback) dir name instead of the intended one.

        The refined plan often uses nouns ('Estruturação', 'Design', 'Validação') without
        any of the trigger verbs ('criar', 'create', 'make', 'build', 'develop'), so the
        regex falls back to slugifying the whole string and produces garbage like
        'refined-plan-pedido-original'.
        """
        # Plan text that uses only nouns / non-trigger verbs (realistic case)
        context_prefixed = (
            "[REFINED PLAN]:\nPEDIDO ORIGINAL:\n[USER REQUEST]:\nquero um app de calculadora\n"
            "PLANO REFINADO:\n1. Estruturação do HTML.\n2. Design da Interface.\n"
            "3. Implementação da Lógica.\n4. Validação e Testes.\n\n"
            "[USER REQUEST]:\nquero um app de calculadora"
        )
        result = _infer_project_dir_from_request(context_prefixed)
        assert result != "app-de-calculadora", (
            "Expected a wrong dir name from context-prefixed input (this validates the bug exists "
            "when user_request_for_dir is NOT used)."
        )

    def test_execute_subplans_uses_user_request_for_dir(self):
        """execute_subplans must use user_request_for_dir to name the project dir, ignoring
        any [REFINED PLAN] prefix in original_request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                fake_executor = FakeExecutorBlock(_ok_result())
                context_prefixed = "[REFINED PLAN]:\nsome plan\n\n[USER REQUEST]:\nquero criar um app de calculadora"

                with patch("abcode.executor.make_executor_block", return_value=fake_executor), \
                     patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")):
                    _run(execute_subplans(
                        subplans=[_sp("SP-1", "Init project")],
                        original_request=context_prefixed,
                        model="fake-model",
                        user_request_for_dir="quero criar um app de calculadora",
                    ))

                created_dirs = [p.name for p in Path(tmpdir).iterdir() if p.is_dir()]
                assert len(created_dirs) == 1
                assert created_dirs[0] == "app-de-calculadora", (
                    f"Expected 'app-de-calculadora', got '{created_dirs[0]}'. "
                    "user_request_for_dir was not used to derive the project dir."
                )
            finally:
                os.chdir(original_cwd)

    def test_execute_subplans_falls_back_to_original_request_when_no_user_request_for_dir(self):
        """When user_request_for_dir is omitted, original_request is used as before."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                fake_executor = FakeExecutorBlock(_ok_result())

                with patch("abcode.executor.make_executor_block", return_value=fake_executor), \
                     patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")):
                    _run(execute_subplans(
                        subplans=[_sp("SP-1", "Init project")],
                        original_request="create a todo app",
                        model="fake-model",
                        # user_request_for_dir not passed
                    ))

                created_dirs = [p.name for p in Path(tmpdir).iterdir() if p.is_dir()]
                assert len(created_dirs) == 1
                assert "todo" in created_dirs[0], (
                    f"Expected dir containing 'todo', got '{created_dirs[0]}'."
                )
            finally:
                os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# 2. Timeout (60 s)
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_hanging_subplan_times_out_and_records_error(self):
        """A subplan whose executor never returns must be cancelled and the
        error stored in results, not bubble up as an unhandled exception.

        We force asyncio.wait_for to use a 1-second timeout so the test is fast.
        asyncio is imported at call-site inside executor.py, so we patch the
        global asyncio.wait_for used by that module via the 'asyncio' namespace.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                hanging = HangingExecutorBlock()

                # Patch asyncio.wait_for so it always uses a 1-second timeout
                # regardless of what the executor passes.
                original_wait_for = asyncio.wait_for

                async def fast_wait_for(coro, timeout):
                    return await original_wait_for(coro, timeout=1.0)

                with patch("abcode.executor.make_executor_block", return_value=hanging), \
                     patch("abcode.skills.get_relevant_skills_llm", new=AsyncMock(return_value="")), \
                     patch("abcode.executor.DEFAULT_MAX_RETRIES", 1), \
                     patch("asyncio.wait_for", side_effect=fast_wait_for):

                    results = _run(execute_subplans(
                        subplans=[_sp("SP-1", "Init project")],
                        original_request="create a calculator app",
                        model="fake-model",
                    ))

                assert "SP-1" in results
                assert "Timeout" in results["SP-1"] or "FAILED" in results["SP-1"], (
                    f"Expected timeout/failure message in results['SP-1'], got: {results['SP-1']}"
                )
            finally:
                os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# 3. Banned server commands in the task prompt
# ---------------------------------------------------------------------------

class TestBannedServerCommands:
    BANNED = [
        "python -m http.server",
        "http-server",
        "npm run dev",
        "flask run",
        "uvicorn",
        "gunicorn",
    ]

    def _get_prompt(self) -> str:
        sp = _sp("SP-1", "Test calculator")
        return _build_task(
            sp,
            original_request="create a calculator app",
            context="PROJECT_DIR: .\nFiles: index.html",
            global_skills_context="",
            cwd="/workspace/calculator-app",
            project_dir=".",
        )

    def test_prompt_forbids_python_http_server(self):
        prompt = self._get_prompt()
        assert "python -m http.server" in prompt, (
            "Task prompt must explicitly forbid 'python -m http.server'."
        )

    def test_prompt_forbids_http_server_tool(self):
        prompt = self._get_prompt()
        assert "http-server" in prompt, (
            "Task prompt must explicitly forbid 'http-server'."
        )

    def test_prompt_forbids_uvicorn(self):
        prompt = self._get_prompt()
        assert "uvicorn" in prompt, (
            "Task prompt must explicitly forbid 'uvicorn'."
        )

    def test_prompt_requires_subprocess_timeout(self):
        prompt = self._get_prompt()
        assert "timeout=30" in prompt, (
            "Task prompt must instruct the LLM to pass timeout=30 to subprocess.run."
        )

    def test_prompt_still_forbids_npm_start(self):
        """Regression: the original ban on npm start must still be present."""
        prompt = self._get_prompt()
        assert "npm start" in prompt or "npm run dev" in prompt, (
            "Task prompt must still forbid npm server commands."
        )
