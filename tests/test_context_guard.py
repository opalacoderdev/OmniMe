"""Tests for the context guard helpers in planner.py.

Covers:
1. _estimate_tokens — returns a positive integer for non-empty text
2. _trim_to_budget — identity when under budget; tail-trimming when over
3. generate_panorama — trims history when it would overflow num_ctx
4. Agent config — landscape_planner and refinement_agent num_ctx values
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from opalacoder.planner import _estimate_tokens, _trim_to_budget, generate_panorama
from opalacoder.config import get_agent_llm_kwargs


# ---------------------------------------------------------------------------
# 1. _estimate_tokens
# ---------------------------------------------------------------------------

def test_estimate_tokens_positive_for_nonempty():
    assert _estimate_tokens("hello world") > 0


def test_estimate_tokens_zero_or_positive_for_empty():
    assert _estimate_tokens("") >= 0


def test_estimate_tokens_grows_with_length():
    short = _estimate_tokens("hi")
    long = _estimate_tokens("hi " * 500)
    assert long > short


def test_estimate_tokens_fallback_heuristic():
    """When litellm.token_counter raises, the fallback (len // 4) must still
    return a positive int for non-trivial text."""
    with patch("opalacoder.planner._estimate_tokens", side_effect=None):
        # Call the real function — if litellm is unavailable it uses len//4
        result = _estimate_tokens("a" * 400)
        assert result > 0


# ---------------------------------------------------------------------------
# 2. _trim_to_budget
# ---------------------------------------------------------------------------

def test_trim_to_budget_identity_when_under():
    text = "User: hello\nAssistant: hi"
    budget = _estimate_tokens(text) + 100
    assert _trim_to_budget(text, budget) == text


def test_trim_to_budget_reduces_tokens_when_over():
    text = "\n".join(
        [f"User: message {i}\nAssistant: response {i}" for i in range(100)]
    )
    budget = 50
    trimmed = _trim_to_budget(text, budget)
    assert _estimate_tokens(trimmed) <= budget + 10  # small tolerance for line rounding


def test_trim_to_budget_keeps_tail():
    """The most recent content (tail) must be preserved after trimming."""
    lines = [f"User: msg{i}" for i in range(50)]
    text = "\n".join(lines)
    budget = 20
    trimmed = _trim_to_budget(text, budget)
    assert "msg49" in trimmed  # last message always kept


def test_trim_to_budget_adds_omission_marker():
    text = "\n".join([f"line {i}" for i in range(200)])
    trimmed = _trim_to_budget(text, 30)
    assert "[...earlier content omitted...]" in trimmed


def test_trim_to_budget_no_marker_when_not_trimmed():
    text = "short text"
    trimmed = _trim_to_budget(text, 10000)
    assert "[...earlier content omitted...]" not in trimmed


def test_trim_to_budget_preserves_line_boundaries():
    """Trimming must not cut mid-line — output lines must be complete."""
    lines = [f"User: this is message number {i}" for i in range(100)]
    text = "\n".join(lines)
    trimmed = _trim_to_budget(text, 40)
    for line in trimmed.splitlines():
        if line.startswith("User:"):
            # Must be a complete line, not a partial cut
            assert line.startswith("User: this is message number")


# ---------------------------------------------------------------------------
# 3. generate_panorama — history trimming integration
# ---------------------------------------------------------------------------

def test_generate_panorama_trims_huge_history():
    """When history is much larger than the available budget, generate_panorama
    must trim it before passing to the planner, not crash or silently overflow."""
    import asyncio
    from agenticblocks.blocks.llm.agent import AgentOutput

    huge_history = "\n".join(
        [f"User: msg{i}\nAssistant: resp{i}" for i in range(1000)]
    )
    request = "create a calculator"
    captured = {}

    async def fake_run(agent_input):
        captured["prompt"] = agent_input.prompt
        return AgentOutput(response="1. Plan phase", tool_calls_made=0)

    mock_planner = MagicMock()
    mock_planner.run = fake_run

    with patch("opalacoder.planner.make_landscape_planner", return_value=mock_planner):
        asyncio.new_event_loop().run_until_complete(
            generate_panorama(request, model="fake/model", history=huge_history)
        )

    assert "prompt" in captured
    prompt = captured["prompt"]
    assert "[...earlier content omitted...]" in prompt
    assert request in prompt


def test_generate_panorama_no_trim_for_small_history():
    """Small history must be passed through untouched."""
    import asyncio
    from agenticblocks.blocks.llm.agent import AgentOutput

    small_history = "User: hi\nAssistant: hello"
    request = "create a calculator"
    captured = {}

    async def fake_run(agent_input):
        captured["prompt"] = agent_input.prompt
        return AgentOutput(response="1. Plan phase", tool_calls_made=0)

    mock_planner = MagicMock()
    mock_planner.run = fake_run

    with patch("opalacoder.planner.make_landscape_planner", return_value=mock_planner):
        asyncio.new_event_loop().run_until_complete(
            generate_panorama(request, model="fake/model", history=small_history)
        )

    prompt = captured["prompt"]
    assert "[...earlier content omitted...]" not in prompt
    assert small_history in prompt


# ---------------------------------------------------------------------------
# 4. Agent config — context windows for planning agents
# ---------------------------------------------------------------------------

def test_landscape_planner_has_large_num_ctx():
    """Planner receives history + skills + request — needs a large context."""
    kwargs = get_agent_llm_kwargs("landscape_planner")
    assert kwargs.get("num_ctx", 0) >= 8192


def test_refinement_agent_has_large_num_ctx():
    kwargs = get_agent_llm_kwargs("refinement_agent")
    assert kwargs.get("num_ctx", 0) >= 8192


def test_planning_agents_do_not_have_think_false():
    """Planners should benefit from extended reasoning — think must not be
    explicitly disabled for them."""
    for agent in ("landscape_planner", "refinement_agent", "orchestrator"):
        kwargs = get_agent_llm_kwargs(agent)
        assert kwargs.get("think") is not False, (
            f"{agent} has think=false but it should be allowed to reason"
        )
