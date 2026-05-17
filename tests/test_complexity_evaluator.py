import pytest

def _classify_complexity(raw_response: str) -> str:
    raw_comp = raw_response.strip().lower()
    if "alternative" in raw_comp:
        return "alternative"
    return "default"

def test_complexity_evaluator_exact_match():
    assert _classify_complexity("alternative") == "alternative"
    assert _classify_complexity("default") == "default"

def test_complexity_evaluator_with_punctuation():
    assert _classify_complexity("alternative.") == "alternative"
    assert _classify_complexity("Alternative!") == "alternative"
    assert _classify_complexity("**alternative**") == "alternative"
    assert _classify_complexity("The task is alternative") == "alternative"

def test_complexity_evaluator_fallback_to_default():
    assert _classify_complexity("I don't know") == "default"
    assert _classify_complexity("") == "default"
    assert _classify_complexity("def") == "default"

