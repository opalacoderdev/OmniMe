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
    "confirmation_agent",
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
def test_classifier_has_think_false(agent):
    """Classifier agents must disable gemma4 thinking mode.
    Without think=false, gemma4 returns empty content via the OpenAI-compatible
    endpoint (ollama issue #15288), causing silent misclassification."""
    kwargs = get_agent_llm_kwargs(agent)
    assert kwargs.get("think") is False, (
        f"{agent} must have think=false to work correctly with ollama/gemma4"
    )


@pytest.mark.parametrize("agent", PLANNING_AGENTS)
def test_planning_agent_does_not_disable_thinking(agent):
    """Planning agents should not have think=false — extended reasoning improves
    the quality of plans and execution strategies."""
    kwargs = get_agent_llm_kwargs(agent)
    assert kwargs.get("think") is not False, (
        f"{agent} must not have think=false"
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

@pytest.mark.parametrize("agent", ["intent_classifier", "confirmation_agent"])
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
