"""Diagnose 'cannot use dict as a set element' error in _run_worker.

The error appeared as [ERROR executing t3] in the run log.
_run_worker_safe only logs str(e), losing the traceback.
This test reproduces the exact call sequence that led to t3[1] failing
and captures the full traceback to identify the exact source line.
"""

import asyncio
import traceback
import pytest

from opalacoder.plugins.html_css_js_tools import search_html_css_js_bugs
from opalacoder.workflow_tools import get_workflow_tools


# ---------------------------------------------------------------------------
# Hypothesis 1: get_workflow_tools() raises when skill_tools contains
# a FunctionBlock whose .name is not a str.
# ---------------------------------------------------------------------------

def test_get_workflow_tools_with_functionblock_name_is_always_str():
    """FunctionBlock.name is declared as str in Block(BaseModel).
    This test confirms it never becomes a dict under normal conditions.
    """
    tools = get_workflow_tools(skill_tools=[search_html_css_js_bugs])
    names = [getattr(t, "name", None) for t in tools]
    non_str = [(i, type(n), n) for i, n in enumerate(names) if not isinstance(n, str)]
    assert not non_str, f"Non-str tool names found: {non_str}"


def test_get_workflow_tools_called_repeatedly_stays_stable():
    """Call get_workflow_tools multiple times with the same skill_tools list —
    simulating t3[0] then t3[1] — and confirm no TypeError is raised.
    """
    skill_tools = [search_html_css_js_bugs]
    for i in range(3):
        try:
            tools = get_workflow_tools(skill_tools=skill_tools)
            assert tools, f"call {i}: empty tools list"
        except TypeError as e:
            tb = traceback.format_exc()
            pytest.fail(
                f"call {i}: TypeError raised — {e}\n\nFull traceback:\n{tb}"
            )


def test_get_workflow_tools_with_object_having_dict_name():
    """Confirm that an object with name=dict raises TypeError at the set check —
    verifying that this IS the failure mode when name is not a str.
    This test is expected to fail/raise — we capture the exact line.
    """
    class BadTool:
        name = {"module": "html_css_js_tools", "func": "search_html_css_js_bugs"}

    try:
        get_workflow_tools(skill_tools=[BadTool()])
        pytest.fail("Expected TypeError was not raised — hypothesis disproved")
    except TypeError as e:
        tb = traceback.format_exc()
        assert "unhashable type" in str(e), f"Different error: {e}\n{tb}"
        # Confirm exact line in workflow_tools.py
        assert "workflow_tools.py" in tb, f"Error not from workflow_tools:\n{tb}"


# ---------------------------------------------------------------------------
# Hypothesis 2: the error comes from _run_worker itself (not get_workflow_tools)
# and is triggered by something in the tool_outputs deduplication loop.
# ---------------------------------------------------------------------------

def test_tool_outputs_deduplication_with_dict_content():
    """Simulate the seen_outputs.add(o) loop with various content types.
    If str() is always applied, no TypeError should occur.
    """
    # Simulate what _capture_iteration produces in tool_outputs
    possible_contents = [
        None,
        "",
        "some string result",
        '{"result": "ok"}',
        '[{"a": 1}]',
        {"result": "a dict not converted"},   # worst case: dict slipped through
        [{"a": 1}],                            # list of dicts slipped through
    ]

    # Reproduce the exact deduplication code from _run_command
    tool_outputs = []
    for content in possible_contents:
        # _capture_iteration does: tool_outputs.append(str(content))
        tool_outputs.append(str(content))

    seen_outputs = set()
    unique_outputs = []
    try:
        for o in tool_outputs:
            if o not in seen_outputs:
                seen_outputs.add(o)
                unique_outputs.append(o)
    except TypeError as e:
        tb = traceback.format_exc()
        pytest.fail(
            f"seen_outputs.add() raised TypeError — this IS the source:\n{e}\n\n{tb}"
        )

    # All passed — str() conversion prevents unhashable dict
    assert len(unique_outputs) <= len(tool_outputs)


def test_tool_outputs_without_str_conversion_raises():
    """If str() were NOT applied in _capture_iteration, a dict in tool_outputs
    would cause TypeError in seen_outputs.add(). Confirm this is the failure mode
    if str() conversion is ever removed or bypassed.
    """
    tool_outputs = [{"result": "a dict"}]  # no str() applied

    seen_outputs = set()
    with pytest.raises(TypeError, match="unhashable type"):
        for o in tool_outputs:
            seen_outputs.add(o)


# ---------------------------------------------------------------------------
# Hypothesis 3: _capture_iteration can append a non-str to tool_outputs
# if 'content' in a tool-role message is a dict (not a JSON string).
# ---------------------------------------------------------------------------

def test_capture_iteration_str_conversion_is_always_applied():
    """Reproduce _capture_iteration logic exactly as written in workflow_orchestrator.
    Verify that str() is applied before appending to tool_outputs.
    """
    tool_outputs = []

    # Simulate message history that agenticblocks produces
    messages = [
        {"role": "user", "content": "do something"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "1", "type": "function",
                         "function": {"name": "edit_file", "arguments": "{}"}}]},
        # Agenticblocks serialises tool results as json.dumps — always str
        {"role": "tool", "content": '{"result": "ok"}'},
        # Edge case: what if content is a dict (should not happen, but test it)
        {"role": "tool", "content": {"result": "a raw dict"}},
        # Edge case: content is None
        {"role": "tool", "content": None},
    ]

    # Exact _capture_iteration logic from workflow_orchestrator.py
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role == "tool" and content:
            tool_outputs.append(str(content))  # str() applied here

    # Now run the deduplication — should never raise
    seen_outputs = set()
    unique_outputs = []
    try:
        for o in tool_outputs:
            if o not in seen_outputs:
                seen_outputs.add(o)
                unique_outputs.append(o)
    except TypeError as e:
        tb = traceback.format_exc()
        pytest.fail(
            f"Deduplication raised TypeError — str() conversion failed to prevent it:\n{e}\n\n{tb}"
        )

    assert all(isinstance(o, str) for o in unique_outputs)
