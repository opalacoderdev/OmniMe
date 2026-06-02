"""JSON-based stdin/stdout protocol for calling OpalaCoder agents."""

import sys
import json
import asyncio
import os
import inspect

# Save real stdout and redirect sys.stdout to sys.stderr to prevent pollution
_real_stdout = sys.stdout
sys.stdout = sys.stderr

# Hook to intercept event prints (e.g. for Python GUI server)
event_hook = None

# Pending GUI input requests: maps request-id -> asyncio.Future so that the
# /api/opalacoder/input_response endpoint can resolve them.
_gui_input_pending: dict = {}

def print_event(event: str, data: dict):
    payload = {"event": event, **data}
    _real_stdout.write(json.dumps(payload) + "\n")
    _real_stdout.flush()
    if event_hook:
        event_hook(payload)

# Import project components safely
try:
    import opalacoder.orchestrator  # resolve circular import order
except ImportError:
    pass

from opalacoder.config import DEFAULT_MODEL, DEFAULT_DB_PATH
from opalacoder.project import ProjectStore, ProjectData
from opalacoder.agents import make_landscape_planner, make_refinement_agent
from opalacoder.memgpt_runtime import build_chat_orchestrator
from agenticblocks.blocks.llm.agent import AgentInput, LLMAgentBlock
from agenticblocks.core.function_block import as_tool

# Import all tools
from opalacoder.tools import (
    read_file as raw_read_file_base,
    write_file,
    run_command,
    run_interactive_command,
    search_code,
    ask_human,
    get_project_overview,
    get_file_overview,
    write_content_pos,
    read_content_pos,
    search_bugs,
    set_project_context,
)
from opalacoder.workflow_tools import (
    read_file as raw_read_file_workflow,
    edit_file,
    replace_lines,
    find_symbol,
    find_callers,
    send_message,
    get_workflow_tools,
)

# Global map of available tools by name
ALL_TOOLS_MAP = {
    "read_file": raw_read_file_workflow,
    "read_file_base": raw_read_file_base,
    "write_file": write_file,
    "run_command": run_command,
    "run_interactive_command": run_interactive_command,
    "search_code": search_code,
    "ask_human": ask_human,
    "get_project_overview": get_project_overview,
    "get_file_overview": get_file_overview,
    "write_content_pos": write_content_pos,
    "read_content_pos": read_content_pos,
    "search_bugs": search_bugs,
    "edit_file": edit_file,
    "replace_lines": replace_lines,
    "find_symbol": find_symbol,
    "find_callers": find_callers,
    "send_message": send_message,
}

# State for persistent session
current_project = None
current_store = None
current_memgpt = None

def wrap_tool(original_tool):
    """Wrap a tool to output events on call and completion."""
    from pydantic import BaseModel
    from agenticblocks.core.function_block import FunctionBlock
    
    if not hasattr(original_tool, "run"):
        name = getattr(original_tool, "name", None) or getattr(original_tool, "__name__", None)
        desc = getattr(original_tool, "description", None) or getattr(original_tool, "__doc__", None)
        original_tool = FunctionBlock(original_tool, name=name, description=desc)
        
    name = getattr(original_tool, "name", None) or getattr(original_tool, "__name__", None)
    original_run = original_tool.run
    
    async def wrapped_run(*args, **kwargs) -> BaseModel:
        # Resolve the input_data (BaseModel) correctly
        if args and isinstance(args[0], BaseModel):
            input_data = args[0]
        elif "input" in kwargs and isinstance(kwargs["input"], BaseModel):
            input_data = kwargs["input"]
        else:
            # Fallback if args/kwargs don't match expected pattern
            raise TypeError("wrapped_run expects a Pydantic BaseModel as its first argument or 'input' keyword argument.")
            
        dump_kwargs = input_data.model_dump()
        print_event("tool_call", {"tool": name, "arguments": dump_kwargs})
        try:
            result = await original_run(input_data)
            if hasattr(result, "result"):
                res_val = result.result
            else:
                res_val = result.model_dump()
            
            res_str = str(res_val)
            if "STDERR:" in res_str or "Error" in res_str:
                print_event("problem", {"tool": name, "message": res_str, "severity": "error"})
        except Exception as e:
            res_val = f"Error: {e}"
            print_event("problem", {"tool": name, "message": str(e), "severity": "error"})
            raise
        finally:
            print_event("tool_result", {"tool": name, "result": str(res_val)})
        return result
        
    object.__setattr__(original_tool, "run", wrapped_run)
    return original_tool



# Monkey-patch get_workflow_tools to automatically wrap tools returned to sub-agents
original_get_workflow_tools = get_workflow_tools

def patched_get_workflow_tools(skill_tools=None):
    tools = original_get_workflow_tools(skill_tools=skill_tools)
    return [wrap_tool(t) for t in tools]

import opalacoder.workflow_tools
import opalacoder.memgpt_runtime
opalacoder.workflow_tools.get_workflow_tools = patched_get_workflow_tools
opalacoder.memgpt_runtime.get_workflow_tools = patched_get_workflow_tools

async def handle_load_project(data: dict):
    global current_project, current_store, current_memgpt
    project_name = data.get("project_name") or "stdin_project"
    project_path = data.get("project_path") or os.getcwd()
    db_path = data.get("db") or DEFAULT_DB_PATH
    
    current_store = ProjectStore(db_path=db_path)
    if current_store.exists(project_name):
        current_project = current_store.load(project_name)
        if data.get("project_path"):
            current_project.project_path = os.path.abspath(project_path)
    else:
        current_project = ProjectData(
            name=project_name,
            project_name=project_name,
            project_path=os.path.abspath(project_path),
        )
    
    # Initialize workspace context
    set_project_context(current_project, current_store)
    
    # Rebuild orchestrator
    current_memgpt = build_chat_orchestrator(current_project, current_store)
    
    print_event("project_loaded", {
        "project_name": current_project.project_name,
        "project_path": current_project.project_path,
        "skills": current_project.skills
    })

async def handle_run(data: dict):
    global current_project, current_store, current_memgpt
    agent_type = data.get("agent") or "chat_orchestrator"
    model = data.get("model")
    system_prompt = data.get("system_prompt")
    prompt = data.get("prompt", "")
    messages_history = data.get("messages", [])
    requested_tools = data.get("tools")
    
    # Setup project context if provided
    if "project_path" in data or "project_name" in data:
        await handle_load_project(data)

    if current_project and current_project.project_path:
        state_dir = os.path.join(current_project.project_path, ".opalacoder")
        os.makedirs(state_dir, exist_ok=True)
        state_file = os.path.join(state_dir, "_editor_state.json")
        editor_state = {
            "current_file": data.get("current_file", ""),
            "editor_content": data.get("editor_content", ""),
            "selected_text": data.get("selected_text", "")
        }
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(editor_state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save editor state: {e}", file=sys.stderr)
    
    # Intercept and process slash commands (like /help, /undo, /commit)
    if prompt.startswith("/"):
        from opalacoder.cli_commands import REPLState, _registry
        cmd, *args = prompt.split(maxsplit=1)
        if cmd in _registry:
            messages = []
            import opalacoder.terminal as T
            
            # Mock print functions
            orig_success = T.success
            orig_error = T.error
            orig_info = T.info
            orig_warning = T.warning
            orig_confirm = T.confirm
            orig_ask = T.ask
            orig_async_confirm_hook = T._async_confirm_hook
            
            def mock_success(*args_m, **kwargs_m):
                msg = " ".join(str(x) for x in args_m)
                messages.append(f"🟢 {msg}")
            def mock_error(*args_m, **kwargs_m):
                msg = " ".join(str(x) for x in args_m)
                messages.append(f"🔴 {msg}")
            def mock_info(*args_m, **kwargs_m):
                msg = " ".join(str(x) for x in args_m)
                messages.append(f"ℹ️ {msg}")
            def mock_warning(*args_m, **kwargs_m):
                msg = " ".join(str(x) for x in args_m)
                messages.append(f"⚠️ {msg}")
            def mock_confirm(prompt: str, default: bool = True) -> bool:
                # Sync fallback — kept for safety, but commands now use await T.aconfirm()
                # which will delegate to _gui_confirm_hook below.
                messages.append(f"🔔 {prompt} → {'yes' if default else 'no'} (auto-confirmed)")
                return default
            def mock_ask(prompt: str) -> str:
                messages.append(f"🔔 {prompt} → (no input in GUI mode)")
                return ""

            async def _gui_confirm_hook(prompt: str, default: bool = True) -> bool:
                """Emit input_request event and wait for the frontend Yes/No response."""
                import uuid
                req_id = str(uuid.uuid4())
                print_event("input_request", {
                    "id": req_id,
                    "prompt": prompt,
                    "options": ["yes", "no"],
                    "default": "yes" if default else "no",
                })
                loop = asyncio.get_event_loop()
                fut = loop.create_future()
                _gui_input_pending[req_id] = fut
                try:
                    raw = await asyncio.wait_for(asyncio.shield(fut), timeout=120.0)
                    return raw.strip().lower() in ("yes", "y", "s", "sim", "true", "1")
                except asyncio.TimeoutError:
                    messages.append(f"⚠️ Confirm timed out — using default ({'yes' if default else 'no'}).")
                    return default
                finally:
                    _gui_input_pending.pop(req_id, None)

            T.success = mock_success
            T.error = mock_error
            T.info = mock_info
            T.warning = mock_warning
            T.confirm = mock_confirm
            T.ask = mock_ask
            T._async_confirm_hook = _gui_confirm_hook

            print_event("agent_started", {"agent": "cli_command", "model": ""})
            try:
                state = REPLState(current_project, current_store)
                cmd_args = args[0].split() if args else []
                # Also mock T.console.print to capture lines
                orig_console_print = T.console.print
                import re
                def mock_console_print(*args_c, **kwargs_c):
                    if not args_c:
                        messages.append("")
                        return
                    raw_msg = " ".join(str(x) for x in args_c)
                    
                    # Split by newlines so we format each line individually
                    lines = raw_msg.split('\n')
                    for line in lines:
                        stripped = line.strip()
                        if not stripped:
                            messages.append("")
                            continue
                        
                        # 1. Header mapping
                        if "Comandos Disponíveis" in stripped or "Available commands" in stripped:
                            messages.append("### 🛠️ Comandos Disponíveis\n")
                            continue
                        if "Active skills for this project" in stripped:
                            messages.append("### 🧠 Active skills for this project\n")
                            continue
                        if "Available skills" in stripped:
                            messages.append("### 📚 Available skills\n")
                            continue
                        if "active in this project" in stripped:
                            messages.append(f"\n_({stripped.replace('* = ', '')})_")
                            continue
                            
                        # 2. Match standard menu item with formatting: [color]name[/color] description
                        # fallback matching if Rich formatting tags are present:
                        match_rich = re.match(r'\s*(?:\*\s*)?\[(green|cyan)\]\s*(.*?)\s*\[/\1\]\s*(.*)', line)
                        if match_rich:
                            name = match_rich.group(2).strip()
                            desc = match_rich.group(3).strip()
                            desc = re.sub(r'\[/?\w+\]', '', desc)
                            has_active_star = "*" in line.split("[cyan]")[0] if "[cyan]" in line else False
                            prefix = "⭐ " if has_active_star else "🔹 "
                            messages.append(f"{prefix}**`{name}`** — {desc}")
                            continue
                            
                        # 3. Match raw slash commands without Rich tags: e.g. "  /help     Show help"
                        cmd_match = re.match(r'^\s*(/[a-zA-Z0-9_<> \-\[\]]+?)\s{2,}(.*)$', line)
                        if cmd_match:
                            cmd_name = cmd_match.group(1).strip()
                            cmd_desc = cmd_match.group(2).strip()
                            messages.append(f"🔹 **`{cmd_name}`** — {cmd_desc}")
                            continue
                            
                        # 4. Match raw skills without Rich tags: e.g. "  * chat-orchestrator   Skill description"
                        has_active_star = bool(re.match(r'^\s*\*\s*', line))
                        skill_match = re.match(r'^\s*(?:\*\s*)?([a-zA-Z0-9_\-]+)\s{2,}(.*)$', line)
                        if skill_match:
                            skill_name = skill_match.group(1).strip()
                            skill_desc = skill_match.group(2).strip()
                            prefix = "⭐ " if has_active_star else "🔹 "
                            messages.append(f"{prefix}**`{skill_name}`** — {skill_desc}")
                            continue
                            
                        # Fallback: clean tags and append
                        clean_line = re.sub(r'\[/?\w+\]', '', line)
                        messages.append(clean_line)
                T.console.print = mock_console_print
                
                try:
                    await _registry.dispatch(state, cmd, cmd_args)
                finally:
                    T.console.print = orig_console_print
            except Exception as e:
                messages.append(f"🔴 Erro ao executar comando: {e}")
            finally:
                T.success = orig_success
                T.error = orig_error
                T.info = orig_info
                T.warning = orig_warning
                T.confirm = orig_confirm
                T.ask = orig_ask
                T._async_confirm_hook = orig_async_confirm_hook
                
            response = "\n".join(messages)
            if not response:
                response = f"Comando {cmd} executado com sucesso."
            print_event("agent_response", {"response": response})
            print_event("agent_finished", {})
            return
        else:
            print_event("agent_started", {"agent": "cli_command", "model": ""})
            print_event("agent_response", {"response": f"🔴 Comando desconhecido: {cmd}. Digite /help para ajuda."})
            print_event("agent_finished", {})
            return

    
    # Build agent
    agent = None
    if agent_type == "landscape_planner":
        agent = make_landscape_planner(model=model)
        if system_prompt:
            agent.system_prompt = system_prompt
    elif agent_type == "refinement_agent":
        agent = make_refinement_agent(model=model)
        if system_prompt:
            agent.system_prompt = system_prompt
    elif agent_type == "chat_orchestrator":
        if not current_memgpt:
            # Autoload default project
            await handle_load_project(data)
        agent = current_memgpt
        if system_prompt:
            agent.system_prompt = system_prompt
    else:
        # Custom LLMAgentBlock
        if not system_prompt:
            print_event("error", {"message": "system_prompt is required for custom agent"})
            return
        
        # Resolve tools
        tools_list = []
        if requested_tools:
            if requested_tools == "all":
                tools_list = [wrap_tool(t) for t in ALL_TOOLS_MAP.values()]
            else:
                for tname in requested_tools:
                    if tname in ALL_TOOLS_MAP:
                        tools_list.append(wrap_tool(ALL_TOOLS_MAP[tname]))
                    else:
                        print_event("error", {"message": f"Tool '{tname}' not found"})
        
        agent = LLMAgentBlock(
            name=agent_type or "custom_agent",
            system_prompt=system_prompt,
            model=model or DEFAULT_MODEL,
            tools=tools_list,
        )
    
    # Setup message history if provided (for custom/standard LLMAgentBlock)
    if messages_history and hasattr(agent, "internal_history"):
        agent.internal_history.clear()
        for msg in messages_history:
            agent.internal_history.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
            
    # Setup callback to stream thoughts
    seen_messages = len(agent.internal_history) if hasattr(agent, "internal_history") else 0
    
    def on_iteration_callback(iteration: int, messages: list):
        nonlocal seen_messages
        new_msgs = messages[seen_messages:]
        seen_messages = len(messages)
        for msg in new_msgs:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            if role == "assistant" and content:
                print_event("thought", {"content": content})
                
    if hasattr(agent, "on_iteration"):
        agent.on_iteration = on_iteration_callback
    elif hasattr(agent, "agent") and hasattr(agent.agent, "on_iteration"):
        agent.agent.on_iteration = on_iteration_callback

    print_event("agent_started", {"agent": agent_type, "model": agent.model})
    
    try:
        resp_obj = await agent.run(AgentInput(prompt=prompt))
        response = resp_obj.response.strip() if resp_obj.response else ""
        
        # Save to store if using chat_orchestrator
        if agent_type == "chat_orchestrator" and current_store and current_project:
            current_store.append_message(current_project, "user", prompt)
            if response:
                current_store.append_message(current_project, "assistant", response)
            current_store.save(current_project)
            
        print_event("agent_response", {"response": response})
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print_event("error", {"message": str(e), "trace": err_msg})
        
    print_event("agent_finished", {})

async def handle_list_projects(data: dict):
    db_path = data.get("db") or DEFAULT_DB_PATH
    store = ProjectStore(db_path=db_path)
    projects = store.list_projects()
    print_event("projects_list", {"projects": projects})

async def handle_create_project(data: dict):
    db_path = data.get("db") or DEFAULT_DB_PATH
    store = ProjectStore(db_path=db_path)
    
    project_name = data.get("project_name")
    if not project_name:
        print_event("error", {"message": "project_name is required"})
        return
    
    project_path = data.get("project_path") or os.getcwd()
    description = data.get("description", "")
    model = data.get("model") or DEFAULT_MODEL
    mode = data.get("mode") or "auto"
    skills = data.get("skills", [])
    api_key = data.get("api_key")
    api_base = data.get("api_base")
    
    db_key = project_name.replace(" ", "_").lower()
    if store.exists(db_key):
        db_key = db_key + "_1"
        
    project = store.create(
        name=db_key,
        mode=mode,
        model=model,
        project_name=project_name,
        project_path=os.path.abspath(project_path),
        skills=skills,
        description=description,
        api_key=api_key,
        api_base=api_base,
    )
    print_event("project_created", {
        "project_name": project.project_name,
        "project_path": project.project_path,
        "skills": project.skills,
        "api_key": project.api_key,
        "api_base": project.api_base,
    })

async def handle_update_project(data: dict):
    db_path = data.get("db") or DEFAULT_DB_PATH
    store = ProjectStore(db_path=db_path)
    
    project_name = data.get("project_name")
    if not project_name:
        print_event("error", {"message": "project_name is required"})
        return
    
    if not store.exists(project_name):
        print_event("error", {"message": f"Project '{project_name}' not found"})
        return
        
    project = store.load(project_name)
    if "display_name" in data:
        project.project_name = data["display_name"]
    if "model" in data and data["model"]:
        project.model = data["model"]
    if "alternative_model" in data:
        project.alternative_model = data["alternative_model"]
    if "description" in data:
        project.description = data["description"]
    if "mode" in data and data["mode"]:
        project.mode = data["mode"]
    if "project_path" in data and data["project_path"]:
        project.project_path = os.path.abspath(data["project_path"])
    if "api_key" in data:
        project.api_key = data["api_key"]
    if "api_base" in data:
        project.api_base = data["api_base"]
    if "model_params" in data:
        project.model_params = data["model_params"]
        
    store.save(project)
    print_event("project_updated", {
        "name": project.name,
        "project_name": project.project_name,
        "project_path": project.project_path,
        "model": project.model,
        "alternative_model": project.alternative_model,
        "mode": project.mode,
        "description": project.description,
        "api_key": project.api_key,
        "api_base": project.api_base,
        "model_params": project.model_params,
    })

async def handle_delete_project(data: dict):
    db_path = data.get("db") or DEFAULT_DB_PATH
    store = ProjectStore(db_path=db_path)
    project_name = data.get("project_name")
    if not project_name:
        print_event("error", {"message": "project_name is required"})
        return
    
    if store.exists(project_name):
        store.delete(project_name)
        print_event("project_deleted", {"project_name": project_name})
    else:
        print_event("error", {"message": f"Project '{project_name}' not found"})

async def stdin_server_loop():
    print_event("server_ready", {})
    
    # Read line by line from stdin
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    
    while True:
        try:
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                print_event("error", {"message": "Invalid JSON format"})
                continue
                
            cmd = data.get("command")
            if cmd == "exit":
                print_event("exited", {})
                break
            elif cmd == "load_project":
                await handle_load_project(data)
            elif cmd == "run":
                await handle_run(data)
            elif cmd == "list_projects":
                await handle_list_projects(data)
            elif cmd == "create_project":
                await handle_create_project(data)
            elif cmd == "update_project":
                await handle_update_project(data)
            elif cmd == "delete_project":
                await handle_delete_project(data)
            else:
                print_event("error", {"message": f"Unknown command '{cmd}'"})
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print_event("error", {"message": f"Exception in loop: {e}"})

def start_stdin_server():
    asyncio.run(stdin_server_loop())
