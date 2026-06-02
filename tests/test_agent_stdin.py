"""Tests for the stdin/stdout agent server protocol."""

import json
import io
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from opalacoder.agent_stdin import (
    print_event,
    wrap_tool,
    patched_get_workflow_tools,
    handle_load_project,
)

def test_print_event(monkeypatch):
    """Verify that print_event writes a JSON line containing the event and data to the real stdout."""
    # Create a dummy stream to capture real stdout
    stream = io.StringIO()
    # Temporarily monkeypatch the module's _real_stdout
    import opalacoder.agent_stdin
    monkeypatch.setattr(opalacoder.agent_stdin, "_real_stdout", stream)

    print_event("test_event", {"foo": "bar", "num": 123})
    
    stream.seek(0)
    output = stream.read().strip()
    
    # Verify the printed event is valid JSON and matches expected values
    parsed = json.loads(output)
    assert parsed["event"] == "test_event"
    assert parsed["foo"] == "bar"
    assert parsed["num"] == 123


def test_wrap_tool():
    """Verify that wrap_tool correctly wraps a sync function as an AgenticBlocks tool."""
    # Define a simple function to wrap
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    wrapped = wrap_tool(add)
    assert wrapped.name == "add"
    assert "Add two numbers" in wrapped.description
    
    # We can invoke the wrapped function via its raw _func attribute or directly
    raw = getattr(wrapped, "_func", None) or wrapped
    assert raw(2, 3) == 5


@pytest.mark.asyncio
async def test_wrap_tool_async():
    """Verify that wrap_tool correctly wraps an async function."""
    async def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        await asyncio.sleep(0.001)
        return a * b

    wrapped = wrap_tool(multiply)
    assert wrapped.name == "multiply"
    assert "Multiply two numbers" in wrapped.description
    
    raw = getattr(wrapped, "_func", None) or wrapped
    res = await raw(3, 4)
    assert res == 12


def test_patched_get_workflow_tools():
    """Verify that patched_get_workflow_tools returns wrapped tools."""
    tools = patched_get_workflow_tools()
    assert len(tools) > 0
    # Every tool returned should be wrapped (which can be checked if its function is wrapped)
    # The wrapped function will have the wrapped decorators applied.
    for t in tools:
        assert hasattr(t, "name")
        assert hasattr(t, "description")


@pytest.mark.asyncio
async def test_project_handlers(tmp_path, monkeypatch):
    """Test project listing, creation, and deletion via stdin handlers."""
    from opalacoder.agent_stdin import handle_create_project, handle_list_projects, handle_delete_project
    
    db_file = str(tmp_path / "test_db.sqlite")
    
    # Capture print_event calls
    events = []
    def mock_print_event(event, data):
        events.append((event, data))
        
    import opalacoder.agent_stdin
    monkeypatch.setattr(opalacoder.agent_stdin, "print_event", mock_print_event)
    
    # 1. Create project
    await handle_create_project({
        "db": db_file,
        "project_name": "Test Project",
        "project_path": str(tmp_path),
        "description": "My test desc",
    })
    
    assert len(events) == 1
    assert events[0][0] == "project_created"
    assert events[0][1]["project_name"] == "Test Project"
    
    # 2. List projects
    events.clear()
    await handle_list_projects({
        "db": db_file,
    })
    assert len(events) == 1
    assert events[0][0] == "projects_list"
    assert len(events[0][1]["projects"]) == 1
    assert events[0][1]["projects"][0]["project_name"] == "Test Project"
    
    # 3. Delete project
    events.clear()
    await handle_delete_project({
        "db": db_file,
        "project_name": "test_project", # name field is db key which is lowercase slug
    })
    assert len(events) == 1
    assert events[0][0] == "project_deleted"
    
    # 4. List projects again (should be empty)
    events.clear()
    await handle_list_projects({
        "db": db_file,
    })
    assert len(events) == 1
    assert len(events[0][1]["projects"]) == 0


@pytest.mark.asyncio
async def test_litellm_acompletion_monkeypatch_reasoning_propagation(monkeypatch):
    """Verify that monkey-patched litellm.acompletion extracts and propagates reasoning to active_on_thinking."""
    import litellm
    from unittest.mock import AsyncMock
    import opalacoder.agent_stdin as agent_stdin
    
    # Mock return value of acompletion
    mock_msg = MagicMock()
    mock_msg.content = "<think>Here is some deep thought.</think> Hello!"
    mock_msg.reasoning_content = None
    mock_msg.reasoning = None
    
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    
    # Temporarily override the original non-patched function that the patch calls
    async def dummy_orig_acompletion(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr(agent_stdin, "_orig_acompletion", dummy_orig_acompletion)
    
    # Track reasoning callback calls
    callback_calls = []
    def dummy_callback(reasoning_text):
        callback_calls.append(reasoning_text)
        
    monkeypatch.setattr(agent_stdin, "active_on_thinking", dummy_callback)
    
    # Call the patched completion
    res = await litellm.acompletion(model="test-model", messages=[])
    
    # Ensure it returned the correct message response
    assert res == mock_resp
    # Give any scheduled tasks on the event loop a split second to execute
    await asyncio.sleep(0.01)
    
    # Verify the callback was triggered with the extracted reasoning
    assert len(callback_calls) == 1
    assert callback_calls[0] == "Here is some deep thought."


def test_skip_directories_in_collect_python_files(tmp_path):
    """Verify that _collect_python_files skips tests, opalacoder, skills, and debug directories."""
    from opalacoder.tools import _collect_python_files
    import os
    
    # Create structure
    (tmp_path / "opalacoder").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "debug").mkdir()
    
    # Write python files inside skipped directories
    (tmp_path / "opalacoder" / "main.py").write_text("print('core')")
    (tmp_path / "tests" / "test_app.py").write_text("print('test')")
    (tmp_path / "skills" / "run.py").write_text("print('skill')")
    (tmp_path / "debug" / "debug.py").write_text("print('debug')")
    
    # Write python files in root (should be collected)
    (tmp_path / "app.py").write_text("print('app')")
    
    # Run collector
    collected = _collect_python_files(str(tmp_path), str(tmp_path))
    
    # Assert that only app.py was collected
    collected_basenames = [os.path.basename(f) for f in collected]
    assert "app.py" in collected_basenames
    assert "main.py" not in collected_basenames
    assert "test_app.py" not in collected_basenames
    assert "run.py" not in collected_basenames
    assert "debug.py" not in collected_basenames
    assert len(collected) == 1
