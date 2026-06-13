"""MemGPT runtime for the skills-oriented architecture (docs/specs/02, 06).

This module assembles the fixed **MemGPT chat-orchestrator** and the machinery it
uses to delegate work to skills:

  - ``build_run_skill_tool(memgpt, project_path)`` returns a ``run_skill`` tool
    bound to a MemGPT instance. When the MemGPT calls it, an ephemeral sub-agent
    (LLMAgentBlock) is spawned with the skill's SKILL.md body as its system prompt
    and the workflow tools available, plus an **intercepted** ``send_message``.
  - The interceptor (a wrapper around the sub-agent's ``send_message``) displays
    each message to the user AND records the exchange into the MemGPT's
    ``internal_history`` so the orchestrator stays aware of what happened.
  - ``build_chat_orchestrator(project, store)`` builds the MemGPT itself: the
    framework ``MemGPTAgentBlock`` primed with the ``chat-orchestrator`` SKILL.md,
    the Level-1 metadata of the active skills, the ``run_skill`` tool, and the
    memory tools.

The module is additive: the legacy intent-routing path in cli.py is untouched
until the REPL is switched over (Phase 4).
"""
from __future__ import annotations
from opalacoder.tools import run_command
import os
from typing import Any

from agenticblocks.blocks.llm.agent import AgentInput, LLMAgentBlock
from agenticblocks.blocks.llm.memgpt_agent import MemGPTAgentBlock
# pyrefly: ignore [missing-import]
from agenticblocks.core.function_block import as_tool

from . import terminal as T

from .tools import (
    ask_human,
    read_core_memory,
    append_core_memory,
    search_conversation_history,
    web_search,
    set_project_context,
)
from .config import (
    DEFAULT_MODEL,
    ALTERNATIVE_MODEL,
    get_agent_llm_kwargs,
    get_agent_max_heartbeats,
    get_agent_model,
    get_agent_response_mode,
    get_project_agent_params,
)
from .skills import (
    active_skills,
    find_skill_dir,
    level1_metadata,
    parse_skill_md,
    MANDATORY_SKILLS,
)

from .tools import get_available_tools

CHAT_ORCHESTRATOR_SKILL = "chat-orchestrator"

_PROVIDER_ALIASES = {"ollama_chat": "ollama"}


def _apply_modelconfig_provider(model: str, project) -> str:
    """If the project has a modelconfig yaml for *model* that declares a
    ``provider`` field, return ``<provider>/<model_name>`` instead of *model*.

    This ensures that e.g. ``ollama/gpt-oss:latest`` is transparently remapped
    to ``ollama_chat/gpt-oss:latest`` when the yaml specifies
    ``provider: ollama_chat`` — without requiring the user to manually save the
    project after loading the modelconfig.
    """
    if not model or "/" not in model:
        return model
    raw_provider, model_name = model.split("/", 1)
    provider_dir = _PROVIDER_ALIASES.get(raw_provider, raw_provider)
    project_path = getattr(project, "project_path", None)
    if not project_path:
        return model
    import yaml as _yaml
    yaml_name = model_name.replace(":", "__") + ".yaml"
    config_path = os.path.join(project_path, ".opalacoder", "modelsconfig", provider_dir, yaml_name)
    if not os.path.isfile(config_path):
        return model
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        new_provider = cfg.get("provider")
        if new_provider and new_provider != raw_provider:
            return f"{new_provider}/{model_name}"
    except Exception:
        pass
    return model


# ---------------------------------------------------------------------------
# Model resolution for a skill's sub-agent
# ---------------------------------------------------------------------------

def resolve_skill_model(skill_meta: dict, project_model: str | None,
                        project_alt: str | None = None) -> str:
    """Resolve the model for a skill's sub-agent from the SKILL.md `model` field.

    "default" → the project's main model; "alternative" → the project's alternative
    model (or the global ALTERNATIVE_MODEL when the project has none); an explicit
    litellm id is used as-is; absent → the project's model (or DEFAULT_MODEL).
    """
    raw = (skill_meta.get("model") or "").strip()
    if not raw:
        return project_model or DEFAULT_MODEL
    if raw == "default":
        return project_model or DEFAULT_MODEL
    if raw == "alternative":
        return project_alt or ALTERNATIVE_MODEL
    return raw


# ---------------------------------------------------------------------------
# Interceptor: sub-agent send_message → user + MemGPT memory
# ---------------------------------------------------------------------------

def make_intercepted_send_message(memgpt: MemGPTAgentBlock, skill_name: str):
    """Return a ``send_message`` tool whose calls are displayed to the user and
    mirrored into *memgpt*'s internal history (docs/specs/06 §4).

    The wrapper is deterministic — it does not depend on model behavior. Each call
    appends a user-visible line and records the exchange so the MemGPT resumes the
    conversation aware of what the sub-agent said.
    """

    @as_tool(
        name="send_message",
        description=(
            "Send a message to the user. Call this to report progress or the final "
            "result. Provide a clear, past-tense summary when the task is complete."
        ),
    )
    def send_message(message: str) -> str:
        # 1. Show to the user (the sub-agent speaks directly).
        T.console.print(f"\n[bold green]OpalaCoder ({skill_name}):[/bold green] {message}\n")
        import json
        print(json.dumps({
            "event": "info",
            "data": {"message": f"[{skill_name}] {message}"}
        }), flush=True)
        
        # 2. Record the message to be returned as the tool result, instead of 
        # injecting a rogue 'assistant' message mid-turn.
        if hasattr(memgpt, "_current_worker_messages"):
            memgpt._current_worker_messages.append(message)
        return "[DONE] message delivered to user"

    return send_message


# ---------------------------------------------------------------------------
# run_skill tool
# ---------------------------------------------------------------------------

def build_run_skill_tool(
    memgpt: MemGPTAgentBlock,
    project_path: str,
    project_model: str | None = None,
    project_alt: str | None = None,
    _project_ref=None,
    _store_ref=None,
):
    """Return a ``run_skill`` tool bound to *memgpt*.

    Calling ``run_skill(skill_name, context, intent)`` resolves the skill directory,
    reads its SKILL.md (Level 2), spawns an ephemeral LLMAgentBlock sub-agent with
    that body as system prompt, the workflow tools, and an intercepted send_message,
    runs it with *context* as the prompt, and returns the sub-agent's result.

    *_project_ref* / *_store_ref* let the tool re-assert the project scope on each
    call (so /load mid-session can't leak writes into the previous project).
    """

    @as_tool(
        name="run_skill",
        description=(
            "Delegate the current task to a skill. Pass the skill name (one of the "
            "available skills shown to you) and a context string with any relevant facts "
            "or instructions you want to give the worker. The worker will automatically "
            "receive the recent chat history as well. The tool returns a summary of what the worker did."
        ),
    )
    async def run_skill(skill_name: str, context: str, intent: str = "newfeat") -> str:
        # Re-assert project scope so the sub-agent's file/terminal tools act inside
        # this project even if a /load changed the global context since build time.
        if _project_ref is not None:
            from .tools import set_project_context as _spc
            _spc(_project_ref, _store_ref)
            
        import json
        print(json.dumps({
            "event": "info",
            "data": {"message": f"Iniciando sub-agente '{skill_name}' em background..."}
        }), flush=True)
        
        skill_dir = find_skill_dir(skill_name, project_path)
        if skill_dir is None:
            return f"[ERROR] skill '{skill_name}' not found."
        meta = parse_skill_md(skill_dir)
        if meta is None:
            return f"[ERROR] skill '{skill_name}' has no valid SKILL.md."

        intent = intent if intent in ("newfeat", "bugfix") else "newfeat"
        model = resolve_skill_model(meta, project_model, project_alt)

        # Write the request to a fixed temp file so the sub-agent never has to
        # shell-quote a complex request (parens/quotes in the request would break
        # `run_command`'s shell=True). The model's command becomes paren-free:
        #   python <abs>/run_workflow.py --request-file <path> --intent <intent>
        request_file = ""
        try:
            _staging = os.path.join(project_path, ".opalacoder")
            os.makedirs(_staging, exist_ok=True)
            request_file = os.path.join(_staging, f"_skill_request_{skill_name}.txt")
            with open(request_file, "w", encoding="utf-8") as _rf:
                _rf.write(context)
        except Exception:
            request_file = ""

        # System prompt = SKILL.md body (Level 2) + working dir scope + exact paths.
        scripts_dir = os.path.join(skill_dir, "scripts")
        scripts_hint = ""
        if os.path.isdir(scripts_dir):
            names = sorted(f for f in os.listdir(scripts_dir) if f.endswith(".py"))
            if names:
                listing = "\n".join(f"  {os.path.join(scripts_dir, n)}" for n in names)
                scripts_hint = (
                    f"\nScripts available in this skill (use the ABSOLUTE path with "
                    f"run_command):\n{listing}\n"
                )
        request_hint = ""
        if request_file:
            request_hint = (
                f"\nThe user's request has been written to this file:\n  {request_file}\n"
                f"When a script needs the request, pass it as --request-file {request_file} "
                f"(do NOT type the request text into the command — use the file).\n"
                f"The intent is: {intent} (pass it as --intent {intent}).\n"
            )
        json_formatting_instruction = (
            "\nCRITICAL: When calling tools (like write_file), you must format your response as a valid JSON block. "
            "Ensure that all double quotes inside JSON string arguments are properly escaped as \\\". "
            "Do NOT write literal backslash-n ('\\n') strings in the code; write the code structure normally "
            "within the JSON string and ensure the JSON format is valid.\n"
        )

        system = (
            "#ROLE: "
            "You are a problem-solving agent. You must use your available tools and skills "
            "to fulfill the user's request provided in your context. "
            "Your specific tools are:\n"
            "  - get_project_overview: Returns the project's folder and file structure. Use it to explore the workspace and locate files.\n"
            "  - read_file: Reads the complete contents of a file. Use it to inspect code or text files entirely.\n"
            "  - read_content_pos: Reads a specific snippet of a file by providing start and end line numbers. Use it for targeted reading of large files.\n"
            "  - write_file: Writes or completely overwrites a file. Use it to create new files or replace existing ones entirely. NEVER use run_command with echo/cat to write files.\n"
            "  - write_content_pos: Modifies a specific block of lines in an existing file. Use it to surgically edit code without replacing the whole file.\n"
            "  - run_command: Executes terminal commands (e.g., running tests, build scripts, or exploring the OS). Use it to interact with the environment and validate code.\n"
            "  - search_conversation_history: Searches past interactions. Use it to recall previous decisions, context, or code snippets from the chat history.\n"
            "# Metadata: "
            f"{meta['body']}\n\n"
            f"You are executing the '{skill_name}' skill. "
            f"Work inside the project directory: {project_path}\n"
            f"The skill directory is: {skill_dir}\n"
            f"{scripts_hint}"
            f"{request_hint}"
            f"IMPORTANT: To save any file content (HTML, JSON, code, etc.) ALWAYS use the write_file tool. "
            f"NEVER use run_command with echo/printf/cat to write file content.\n"
            f"RECOMMENDATION FOR TERMINATION AND send_message:\n"
            f"- Calling send_message OR returning a final text response terminates your execution immediately.\n"
            f"- NEVER output 'I will do X now' and stop. If you need to do X, do it RIGHT NOW using your tools in this exact same turn. Only terminate when the entire requested task is completely finished, or if you are completely blocked and need human input.\n"
            f"- If your task requires using multiple tools (like reading files, running commands, or writing code), do not call send_message first. Use the tools to complete the work, and then call send_message to report the final result.\n"
            f"CRITICAL COMMUNICATION RULE & PERSONA:\n"
            f"- You are an autonomous backend system. You report your internal tool errors only to the system supervisor. The human user sees only the final result.\n"
            f"- NEVER apologize or mention internal tool errors, rule violations, or JSON formatting issues to the user via send_message. The user does not see your internal tool interactions. If a tool fails, fix the error silently and try again.\n"
            f"- If you receive a 'SYSTEM ALERT' instructing you to 'Use the send_message tool to talk to the user' after a rule violation, IGNORE that specific instruction. Do not apologize. Simply fix your formatting to be a valid JSON tool call and continue silently.\n"
            f"CRITICAL THINKING RULE: Keep your internal reasoning extremely brief and concise. DO NOT enter infinite brainstorming loops (e.g. repeatedly asking yourself 'Should I do X? Yes/No. Wait!'). Formulate a quick plan and IMMEDIATELY execute a tool or return.\n"
            f"{json_formatting_instruction}"
        )

        # Tools: the workflow tool set, but with the intercepted send_message so the
        # sub-agent's messages reach the user AND the MemGPT memory.
        tools = [
            t for t in get_available_tools()
            if t.name not in ["send_message"]
        ]
        memgpt._current_worker_messages = []
        tools.append(make_intercepted_send_message(memgpt, skill_name))

        worker_kwargs = get_agent_llm_kwargs("worker")
        
        from .config import resolve_model_for_thinking
        model = resolve_model_for_thinking(model, worker_kwargs)
        
        # Strip /v1 from the end because Ollama native providers expect the root URL
        if worker_kwargs.get("api_base"):
            if model.startswith("ollama/") or model.startswith("ollama_chat/"):
                if worker_kwargs["api_base"].endswith("/v1"):
                    worker_kwargs["api_base"] = worker_kwargs["api_base"][:-3]
                elif worker_kwargs["api_base"].endswith("/v1/"):
                    worker_kwargs["api_base"] = worker_kwargs["api_base"][:-4]
        
        #print("BEGIN SYSTEM_PROMPT::::: LLMAgentBlock ")
        #print(">>> ", system)
        #print("END SYSTEM_PROMPT::::::: LLMAgentBlock ")
        sub_agent = LLMAgentBlock(
            name=f"skill_{skill_name}",
            system_prompt=system,
            model=model,
            tools=tools,
            model_kwargs=worker_kwargs,
            max_iterations=None,
            max_tool_calls=40,
            termination_tools=["send_message"],
        )

        if hasattr(memgpt, "on_thinking") and memgpt.on_thinking:
            sub_agent.on_thinking = memgpt.on_thinking

        os.environ.setdefault(
            "OPALACODER_ROOT",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        # The intent (newfeat/bugfix) the MemGPT classified is surfaced to the
        # sub-agent so script-driven skills can pass it through (e.g. --intent).
        # Automatically inject recent chat history so MemGPT doesn't have to waste tokens copying it
        recent_history = "\n".join([f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}" for m in memgpt.internal_history[-10:] if m.get("role") in ("user", "assistant")])
        prompt = f"INTENT: {intent}\n\nRECENT CHAT HISTORY:\n{recent_history}\n\nMEMGPT CONTEXT/INSTRUCTIONS:\n{context}"
        try:
            out = await sub_agent.run(AgentInput(prompt=prompt))
            out_text = out.response if hasattr(out, "response") else str(out)
            tool_calls = getattr(out, "tool_calls_made", "?")
        except Exception as e:
            out_text = f"[CRITICAL WORKER CRASH] A exceção não tratada interrompeu o worker: {str(e)}"
            tool_calls = "?"

        if "<<NEED_INPUT>>" in out_text:
            parts = out_text.split("<<NEED_INPUT>>", 1)
            user_prompt = parts[1].strip() if len(parts) > 1 else "Please provide required input:"
            user_response = ask_human(user_prompt)
            out_text = out_text.replace("<<NEED_INPUT>>", f"[User provided: {user_response}]")

        # Return the summary of what the worker did to MemGPT
        worker_summary = "\n".join(getattr(memgpt, "_current_worker_messages", []))
        if not worker_summary.strip():
            worker_summary = out_text
            # Se o worker calou a boca e o texto for genérico, alertar o orquestrador que ele pode ter estourado o limite.
            if not worker_summary.strip() or "max iterations reached" in worker_summary.lower():
                worker_summary = f"[AVISO: O worker terminou sem um resumo claro. Ele realizou {tool_calls} chamadas de ferramenta e o último texto gerado foi: {out_text}]"

        import json
        print(json.dumps({
            "event": "info",
            "data": {"message": f"Worker '{skill_name}' finalizado. Relatório:\n{worker_summary}"}
        }), flush=True)

        return f"[skill '{skill_name}' finished] Worker's summary/report:\n(Tools used by worker: {tool_calls})\n{worker_summary}"

    return run_skill


# ---------------------------------------------------------------------------
# Chat-orchestrator (the fixed MemGPT)
# ---------------------------------------------------------------------------

def _chat_orchestrator_body(project_path: str) -> str:
    """Return the chat-orchestrator SKILL.md body, or a minimal fallback."""
    skill_dir = find_skill_dir(CHAT_ORCHESTRATOR_SKILL, project_path)
    if skill_dir:
        meta = parse_skill_md(skill_dir)
        if meta and meta["body"]:
            return meta["body"]
    return (
        "You are the OpalaCoder chat-orchestrator. Converse with the user and, when "
        "a request matches an available skill, call run_skill(skill_name, context)."
    )


def build_chat_orchestrator(project, store=None) -> MemGPTAgentBlock:
    """Build the fixed MemGPT chat-orchestrator for a project.

    The system prompt = chat-orchestrator SKILL.md body + Level-1 metadata of the
    active skills. Tools = run_skill + the memory tools. Uses the framework
    MemGPTAgentBlock (classic memory) per docs/specs/04 §1.
    """
    from .tools import (
        read_core_memory, append_core_memory, search_conversation_history,
        set_project_context,
    )

    project_path = getattr(project, "project_path", "") or os.getcwd()
    project_model = getattr(project, "model", None) or DEFAULT_MODEL
    project_alt = getattr(project, "alternative_model", "") or ALTERNATIVE_MODEL

    # Scope all file/terminal tools to the project directory. Without this,
    # get_project_path() falls back to the cwd (the OpalaCoder repo root) and the
    # sub-agent's write_file/run_command would act outside the project.
    set_project_context(project, store)

    skills = active_skills(project_path)
    metadata = level1_metadata(skills)
    body = _chat_orchestrator_body(project_path)

    project_name = getattr(project, "project_name", "") or getattr(project, "name", "(unknown)")
    project_desc = getattr(project, "description", "") or ""
    project_mode = getattr(project, "mode", "auto") or "auto"
    core_memory = getattr(project, "core_memory", "") or ""

    project_block = (
        f"## Current Project\n"
        f"- **Name**: {project_name}\n"
        f"- **Path**: {project_path}\n"
        f"- **Model**: {project_model}\n"
        f"- **Alt. Model**: {project_alt}\n"
        f"- **Mode**: {project_mode}\n"
    )
    if project_desc:
        project_block += f"- **Description**: {project_desc}\n"
    if core_memory:
        project_block += f"\n### Core Memory (persisted facts)\n{core_memory}\n"

    system_prompt = (
        f"{body}\n\n"
        f"{project_block}\n"
        f"## Available skills (call run_skill with the skill name)\n{metadata}\n"
    )

    model = get_agent_model("memgpt", get_agent_model("chat_agent", project_model))
    model = _apply_modelconfig_provider(model, project)
    _llm_kwargs = get_agent_llm_kwargs("memgpt")
    
    from .config import resolve_model_for_thinking
    model = resolve_model_for_thinking(model, _llm_kwargs)
    
    # Strip /v1 from the end because Ollama native providers expect the root URL
    if _llm_kwargs.get("api_base"):
        if model.startswith("ollama/") or model.startswith("ollama_chat/"):
            if _llm_kwargs["api_base"].endswith("/v1"):
                _llm_kwargs["api_base"] = _llm_kwargs["api_base"][:-3]
            elif _llm_kwargs["api_base"].endswith("/v1/"):
                _llm_kwargs["api_base"] = _llm_kwargs["api_base"][:-4]
                
    _agent_params = get_project_agent_params()

    memgpt = MemGPTAgentBlock(
        name="chat_orchestrator",
        system_prompt=system_prompt,
        model=model,
        tools=[read_core_memory, append_core_memory, search_conversation_history, web_search],
        model_kwargs=_llm_kwargs,
        max_heartbeats=_agent_params.get("max_heartbeats", get_agent_max_heartbeats("memgpt", 20)),
        max_context_tokens=_agent_params.get("max_context_tokens", _llm_kwargs.get("num_ctx", 8192)),
        eviction_threshold=_agent_params.get("eviction_threshold", 1.0),
        memory_pressure_threshold=_agent_params.get("memory_pressure_threshold", 0.7),
        debug=_agent_params.get("debug", False),
        use_shared_router=_agent_params.get("use_shared_router", True),
        response_mode=_agent_params.get("response_mode", get_agent_response_mode("memgpt")),
    )

    #print("BEGIN MEMGPT SYSTEM PROMPT >>>>>>>>>>>>>>")
    #print(system_prompt)
    #print("END MEMGPT SYSTEM PROMPT <<<<<<<<<<<< ")
    

    # Seed the working context from persisted history so the conversation restores
    # across restarts (the old chat_agent did this; the MemGPT starts empty).
    _VALID_ROLES = {"user", "assistant", "system", "tool"}
    history = getattr(project, "history", None) or []
    for msg in history[-10:]:
        role = msg.get("role", "assistant")
        if role not in _VALID_ROLES:
            role = "assistant"
        memgpt.internal_history.append({"role": role, "content": msg.get("content", "")})

    # run_skill is bound to this MemGPT instance (interceptor needs its history)
    # and to the project (so it can re-scope file tools on each call).
    run_skill = build_run_skill_tool(
        memgpt, project_path, project_model, project_alt,
        _project_ref=project, _store_ref=store,
    )
    memgpt.tools = list(memgpt.tools) + [run_skill]
    return memgpt
