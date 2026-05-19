"""Tests for the intent classifier.

Covers:
1. Agent config — think=false, max_tokens, num_ctx read from agents.yaml
2. System prompt — must not embed history or project context
3. Fallback — empty LLM response must NOT default to 'plan'
4. Classification — correct label for representative inputs (integration, needs ollama)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from opalacoder.agents import make_intent_classifier
from opalacoder.config import get_agent_llm_kwargs
from agenticblocks.blocks.llm.agent import AgentInput, AgentOutput


# ---------------------------------------------------------------------------
# 1. Agent configuration (agents.yaml)
# ---------------------------------------------------------------------------

def test_intent_classifier_disables_thinking():
    """reasoning_effort must be set to a non-thinking value (e.g. 'none') to prevent
    gemma4 from returning output in the reasoning field instead of message.content
    (ollama issue #15288). litellm maps reasoning_effort to the ollama think field."""
    kwargs = get_agent_llm_kwargs("intent_classifier")
    effort = kwargs.get("reasoning_effort")
    assert effort is not None and effort not in {"low", "medium", "high"}, (
        f"reasoning_effort must be set to disable thinking, got {effort!r}"
    )


def test_intent_classifier_has_max_tokens():
    """max_tokens must be present and small to limit cloud API cost."""
    kwargs = get_agent_llm_kwargs("intent_classifier")
    assert "max_tokens" in kwargs
    assert kwargs["max_tokens"] <= 20


def test_intent_classifier_has_small_num_ctx():
    """Classifier only needs a small context window — keeps it fast and cheap."""
    kwargs = get_agent_llm_kwargs("intent_classifier")
    assert kwargs.get("num_ctx", 8192) <= 4096


# ---------------------------------------------------------------------------
# 2. System prompt — must not inject history or project context
# ---------------------------------------------------------------------------

def test_classifier_system_prompt_has_no_history_markers():
    """The system prompt must not reference conversation history.
    History injected into the classifier was the root cause of 'clear' being
    misclassified as 'plan' (the project context appeared inside USER'S NEW MESSAGE)."""
    c = make_intent_classifier()
    prompt = c.system_prompt
    assert "[CONVERSATION HISTORY]" not in prompt
    assert "[END HISTORY]" not in prompt
    assert "[PROJECT:" not in prompt


def test_classifier_system_prompt_lists_all_valid_intents():
    """All five intent labels must appear in the system prompt."""
    c = make_intent_classifier()
    for intent in ("command_hint", "greetings", "question", "plan", "chat"):
        assert intent in c.system_prompt


def test_classifier_system_prompt_lists_clear_as_command():
    """'clear' must be explicitly listed as a command_hint word so the model
    doesn't treat it as a natural-language 'to clear' verb."""
    c = make_intent_classifier()
    assert "clear" in c.system_prompt


# ---------------------------------------------------------------------------
# 3. Fallback — empty response must not trigger 'plan'
# ---------------------------------------------------------------------------

_VALID_INTENTS = {"greetings", "question", "plan", "chat", "command_hint"}


def _classify(raw_response: str) -> str:
    """Replicate the REPL intent-parsing logic from cli.py."""
    _raw = raw_response.strip().lower()
    intent = _raw.split()[0].strip(".,!?*\"'") if _raw else ""
    if not intent or intent not in _VALID_INTENTS:
        return "__unclear__"
    return intent


def test_empty_response_does_not_yield_plan():
    """An empty LLM response must not fall through to 'plan' (which triggers
    run_pipeline). It should yield a sentinel that the REPL handles with a
    clarification prompt."""
    assert _classify("") != "plan"


def test_empty_response_yields_unclear_sentinel():
    assert _classify("") == "__unclear__"


def test_unknown_word_response_yields_unclear_sentinel():
    assert _classify("i_dont_know") == "__unclear__"


def test_valid_intents_are_parsed_correctly():
    for intent in _VALID_INTENTS:
        assert _classify(intent) == intent


def test_intent_with_punctuation_is_stripped():
    assert _classify("plan.") == "plan"
    assert _classify("chat!") == "chat"


def test_empty_llm_response_triggers_clarification():
    """When the LLM returns an empty response, the REPL must NOT call run_pipeline.
    We verify by feeding an empty response through the same parsing logic used in cli.py."""
    import asyncio

    async def _empty_run(self, _input):
        return AgentOutput(response="", tool_calls_made=0)

    with patch("agenticblocks.blocks.llm.agent.LLMAgentBlock.run", new=_empty_run):
        classifier = make_intent_classifier()
        result = asyncio.new_event_loop().run_until_complete(
            classifier.run(AgentInput(prompt="clear"))
        )

    intent = _classify(result.response)
    assert intent == "__unclear__", (
        "Empty response must yield unclear, not trigger run_pipeline"
    )


# ---------------------------------------------------------------------------
# 4. Classification correctness (integration — requires local ollama)
# ---------------------------------------------------------------------------

CLASSIFICATION_CASES = [
    # (input, expected_intent)
    ("clear", "command_hint"),
    ("help", "command_hint"),
    ("exit", "command_hint"),
    ("hi", "greetings"),
    ("hello there", "greetings"),
    ("what does async mean?", "question"),
    ("how does this function work?", "question"),
    ("create a calculator", "plan"),
    ("O botão = da calculadora não está funcionando", "plan"),
    ("fix the login bug", "plan"),
    ("that's interesting", "chat"),
]


@pytest.mark.integration
@pytest.mark.parametrize("user_input,expected", CLASSIFICATION_CASES)
def test_classifier_labels(user_input, expected):
    """End-to-end classification against the real ollama model."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=0.5)
    except Exception:
        pytest.skip("Ollama is not running/reachable.")

    classifier = make_intent_classifier()

    async def run():
        return await classifier.run(AgentInput(prompt=user_input))

    result = asyncio.new_event_loop().run_until_complete(run())
    assert result.response != "", f"Model returned empty response for: {user_input!r}"
    intent = _classify(result.response)
    assert intent == expected, (
        f"Input {user_input!r}: expected {expected!r}, got {intent!r} "
        f"(raw: {result.response!r})"
    )
