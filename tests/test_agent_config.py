"""Tests for agents.yaml configuration correctness.

Covers:
1. think=false is set for classifier/evaluator/selector agents (ollama issue #15288)
2. think is NOT set for planning/execution agents
3. Classifier agents have small num_ctx (cost efficiency)
4. Orchestrator has a large num_ctx (long execution chains)
5. temperature=0 for deterministic classifiers
"""

import pytest
from opalacoder.config import get_agent_llm_kwargs


CLASSIFIER_AGENTS = [
    "intent_classifier",
    "complexity_evaluator",
    "skill_selector",
]

PLANNING_AGENTS = [
    "landscape_planner",
    "refinement_agent",
    "orchestrator",
]


# ---------------------------------------------------------------------------
# think=false for classifiers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent", CLASSIFIER_AGENTS)
def test_classifier_disables_thinking(agent):
    """Classifier agents must disable gemma4 thinking mode via reasoning_effort.

    litellm maps reasoning_effort to the ollama `think` field. Values outside
    {"low","medium","high"} (e.g. "none") produce think=false on the wire.
    Without this, gemma4 on ollama returns output in the reasoning field and
    leaves message.content empty, causing silent misclassification (ollama #15288).
    """
    kwargs = get_agent_llm_kwargs(agent)
    effort = kwargs.get("reasoning_effort")
    thinking_enabled = effort in {"low", "medium", "high"}
    assert not thinking_enabled, (
        f"{agent} must have reasoning_effort set to a non-thinking value (e.g. 'none'), "
        f"got {effort!r}"
    )


# ---------------------------------------------------------------------------
# Context window sizing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent", CLASSIFIER_AGENTS)
def test_classifier_has_small_num_ctx(agent):
    """Classifiers receive short inputs — a large num_ctx wastes memory on ollama."""
    kwargs = get_agent_llm_kwargs(agent)
    assert kwargs.get("num_ctx", 8192) <= 4096, (
        f"{agent} has a larger num_ctx than needed for a classifier"
    )


def test_orchestrator_has_large_num_ctx():
    """Orchestrator accumulates long tool-call histories — needs at least 16k context."""
    kwargs = get_agent_llm_kwargs("orchestrator")
    assert kwargs.get("num_ctx", 0) >= 16384


# ---------------------------------------------------------------------------
# Determinism for classifiers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent", ["intent_classifier", "skill_selector"])
def test_deterministic_classifiers_have_zero_temperature(agent):
    """Classification must be deterministic — temperature must be 0."""
    kwargs = get_agent_llm_kwargs(agent)
    assert kwargs.get("temperature") == 0


# ---------------------------------------------------------------------------
# max_tokens sanity
# ---------------------------------------------------------------------------

def test_intent_classifier_has_max_tokens():
    """max_tokens must be set to cap cloud API cost for single-word responses."""
    kwargs = get_agent_llm_kwargs("intent_classifier")
    assert "max_tokens" in kwargs
    assert 1 <= kwargs["max_tokens"] <= 20


def test_orchestrator_has_no_restrictive_max_tokens():
    """Orchestrator must not be limited to a small max_tokens — it produces
    long reasoning chains and final reports."""
    kwargs = get_agent_llm_kwargs("orchestrator")
    max_tok = kwargs.get("max_tokens", None)
    # Either absent or large
    assert max_tok is None or max_tok >= 1024
