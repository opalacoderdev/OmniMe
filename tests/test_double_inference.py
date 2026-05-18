import pytest
from opalacoder.config import get_agent_max_heartbeats, _AGENT_OVERRIDES
from opalacoder.agents import make_post_plan_evaluator

def test_get_agent_max_heartbeats_auto(monkeypatch):
    monkeypatch.setitem(_AGENT_OVERRIDES, "orchestrator", {"max_heartbeats": "auto"})
    
    val = get_agent_max_heartbeats("orchestrator", 20)
    assert val == "auto", "Should return 'auto' string when configured"

def test_get_agent_max_heartbeats_int(monkeypatch):
    monkeypatch.setitem(_AGENT_OVERRIDES, "orchestrator", {"max_heartbeats": 100})
    
    val = get_agent_max_heartbeats("orchestrator", 20)
    assert val == 100, "Should return integer when configured"

def test_make_post_plan_evaluator_format():
    evaluator = make_post_plan_evaluator("test-model")
    assert "estimated_steps" in evaluator.system_prompt
    assert "model" in evaluator.system_prompt
    assert evaluator.litellm_kwargs.get("response_format", {}).get("type") == "json_object"
