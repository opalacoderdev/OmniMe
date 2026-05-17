"""Tests for AutonomousOrchestratorStrategy._build_system_prompt.

Verifies that the orchestrator's system prompt:
1. Always forbids starting long-running servers (npm run dev, flask run, etc.)
2. Embeds the project path and name when project_context is provided
3. Embeds the approved plan when one is given
4. Mandates calling get_project_overview as the first action
5. Requires a single send_message call only after all work is done
"""

import pytest
from opalacoder.orchestrator import AutonomousOrchestratorStrategy


@pytest.fixture
def strategy():
    return AutonomousOrchestratorStrategy(model="fake/model")


# ---------------------------------------------------------------------------
# 1. Server ban
# ---------------------------------------------------------------------------

BANNED_COMMANDS = [
    "npm start",
    "npm run dev",
    "flask run",
    "uvicorn",
]

@pytest.mark.parametrize("cmd", BANNED_COMMANDS)
def test_prompt_forbids_server_commands(strategy, cmd):
    """The system prompt must explicitly forbid long-running server commands."""
    prompt = strategy._build_system_prompt()
    assert cmd in prompt, (
        f"System prompt does not forbid '{cmd}'. "
        "The orchestrator might start a server and hang."
    )


# ---------------------------------------------------------------------------
# 2. Project context injection
# ---------------------------------------------------------------------------

def test_prompt_includes_project_name_and_path(strategy):
    """When project_context is provided, the prompt must embed both name and path."""
    ctx = "[PROJECT: MyApp | PATH: /home/user/myapp]"
    prompt = strategy._build_system_prompt(project_context=ctx)
    assert "MyApp" in prompt
    assert "/home/user/myapp" in prompt


def test_prompt_scopes_agent_to_project_path(strategy):
    """The prompt must instruct the agent to stay inside the project path."""
    ctx = "[PROJECT: MyApp | PATH: /home/user/myapp]"
    prompt = strategy._build_system_prompt(project_context=ctx)
    # The rule about exclusive project scope must reference the path
    assert "/home/user/myapp" in prompt
    # Must contain a restriction about not touching files outside
    assert "outside" in prompt.lower() or "exclusively" in prompt.lower() or "Never touch" in prompt


def test_prompt_without_context_has_no_project_section(strategy):
    """When no project_context is passed, there should be no PROJECT CONTEXT header."""
    prompt = strategy._build_system_prompt(project_context="")
    assert "## PROJECT CONTEXT" not in prompt


# ---------------------------------------------------------------------------
# 3. Approved plan injection
# ---------------------------------------------------------------------------

def test_prompt_includes_approved_plan(strategy):
    """When an approved plan is provided, it must appear verbatim in the prompt."""
    plan = "Phase 1: Write index.html\nPhase 2: Write style.css"
    prompt = strategy._build_system_prompt(approved_plan=plan)
    assert plan in prompt


def test_prompt_contains_execute_instruction_when_plan_given(strategy):
    """When a plan is provided, the prompt must instruct the agent to execute it."""
    plan = "Phase 1: Do something"
    prompt = strategy._build_system_prompt(approved_plan=plan)
    assert "Execute" in prompt or "execute" in prompt


def test_prompt_without_plan_has_no_plan_section(strategy):
    """When no plan is given, the APPROVED PLAN header must not appear."""
    prompt = strategy._build_system_prompt(approved_plan="")
    assert "## APPROVED PLAN" not in prompt


# ---------------------------------------------------------------------------
# 4. get_project_overview as mandatory first action
# ---------------------------------------------------------------------------

def test_prompt_mandates_get_project_overview(strategy):
    """The orchestrator must call get_project_overview before anything else."""
    prompt = strategy._build_system_prompt()
    assert "get_project_overview" in prompt


# ---------------------------------------------------------------------------
# 5. Single send_message rule
# ---------------------------------------------------------------------------

def test_prompt_mandates_single_send_message(strategy):
    """The agent must call send_message exactly once, only after finishing all work."""
    prompt = strategy._build_system_prompt()
    assert "send_message" in prompt
    # Must not call send_message prematurely
    assert "exactly once" in prompt or "only after" in prompt.lower() or "NEVER call" in prompt
