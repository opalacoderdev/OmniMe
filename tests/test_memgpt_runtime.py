"""Tests for the MemGPT runtime (skills-oriented architecture, docs/specs/02, 06).

Verifies assembly and wiring WITHOUT invoking any LLM:
  - resolve_skill_model maps default/alternative/explicit/absent correctly
  - build_chat_orchestrator produces a framework MemGPTAgentBlock with run_skill
    and the memory tools, and embeds Level-1 skill metadata in the system prompt
  - the intercepted send_message records into the MemGPT internal history
  - run_skill returns an error for an unknown skill (no LLM needed)
"""

import asyncio
import os

import opalacoder.orchestrator  # noqa: F401  (resolve circular import order)
from opalacoder.memgpt_runtime import (
    resolve_skill_model,
    build_chat_orchestrator,
    build_run_skill_tool,
    make_intercepted_send_message,
)
from opalacoder.project import ProjectData
from opalacoder.config import DEFAULT_MODEL, ALTERNATIVE_MODEL


def _project(tmp_path):
    return ProjectData(
        name="t", project_name="t",
        project_path=str(tmp_path), model="ollama/proj-model",
    )


def test_resolve_skill_model():
    # "default" → the project's main model (falls back to DEFAULT_MODEL when unset).
    assert resolve_skill_model({"model": "default"}, "ollama/x") == "ollama/x"
    assert resolve_skill_model({"model": "default"}, None) == DEFAULT_MODEL
    # "alternative" → the project's alternative model, else the global default.
    assert resolve_skill_model({"model": "alternative"}, "ollama/x") == ALTERNATIVE_MODEL
    assert resolve_skill_model({"model": "alternative"}, "ollama/x", "gemini/proj-alt") == "gemini/proj-alt"
    # Explicit id used as-is; absent → project model.
    assert resolve_skill_model({"model": "ollama/custom"}, "ollama/x") == "ollama/custom"
    assert resolve_skill_model({"model": ""}, "ollama/proj") == "ollama/proj"
    assert resolve_skill_model({}, None) == DEFAULT_MODEL


def test_build_chat_orchestrator_has_run_skill_and_memory_tools(tmp_path):
    m = build_chat_orchestrator(_project(tmp_path), None)
    names = {getattr(t, "name", None) for t in m.tools}
    assert "run_skill" in names
    assert {"read_core_memory", "append_core_memory", "search_conversation_history"} <= names


def test_chat_orchestrator_system_prompt_embeds_skill_metadata(tmp_path):
    m = build_chat_orchestrator(_project(tmp_path), None)
    # Bundled skills must surface as Level-1 metadata for routing.
    assert "Available skills" in m.system_prompt
    assert "chat-orchestrator" in m.system_prompt
    assert "implement-feature" in m.system_prompt


def test_uses_framework_memgpt_block(tmp_path):
    from agenticblocks.blocks.llm.memgpt_agent import MemGPTAgentBlock
    m = build_chat_orchestrator(_project(tmp_path), None)
    assert isinstance(m, MemGPTAgentBlock)


def test_intercepted_send_message_records_into_memgpt(tmp_path):
    m = build_chat_orchestrator(_project(tmp_path), None)
    before = len(m.internal_history)
    sm = make_intercepted_send_message(m, "implement-feature")
    # FunctionBlock wraps the function; call the underlying callable.
    raw = getattr(sm, "_func", None) or sm
    result = raw("Created hello.txt with the requested content.")
    assert "DONE" in result
    assert len(m.internal_history) == before + 1
    last = m.internal_history[-1]
    assert last["role"] == "assistant"
    assert "[skill:implement-feature]" in last["content"]
    assert "hello.txt" in last["content"]


def test_run_skill_unknown_skill_returns_error(tmp_path):
    m = build_chat_orchestrator(_project(tmp_path), None)
    run_skill = build_run_skill_tool(m, str(tmp_path), "ollama/proj")
    raw = getattr(run_skill, "_func", None) or run_skill
    result = asyncio.run(raw("does-not-exist", "context"))
    assert "[ERROR]" in result
    assert "not found" in result


def test_run_skill_accepts_intent_param(tmp_path):
    """run_skill exposes an intent param (MemGPT passes newfeat/bugfix)."""
    import inspect
    m = build_chat_orchestrator(_project(tmp_path), None)
    run_skill = build_run_skill_tool(m, str(tmp_path), "ollama/proj")
    raw = getattr(run_skill, "_func", None) or run_skill
    params = inspect.signature(raw).parameters
    assert "intent" in params
    assert params["intent"].default == "newfeat"


def test_build_chat_orchestrator_scopes_project_path(tmp_path):
    """Regression: building the MemGPT must set the global project context so the
    sub-agent's file tools act inside the project, not the OpalaCoder repo root."""
    from opalacoder.tools import get_project_path
    build_chat_orchestrator(_project(tmp_path), None)
    assert os.path.abspath(get_project_path()) == os.path.abspath(str(tmp_path))
