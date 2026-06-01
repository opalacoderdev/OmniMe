"""REPL command registry and handlers for OpalaCoder CLI."""

from .project import ProjectStore, ProjectData
from . import terminal as T
from .i18n import _
from rich.markup import escape as _escape


# ─── REPL state container ─────────────────────────────────────────────────────

class REPLState:
    def __init__(self, project: ProjectData, store: ProjectStore):
        self.project = project
        self.store = store
        # Skills-oriented architecture: the fixed MemGPT chat-orchestrator, built
        # once per session (classic memory accumulates across turns) and rebuilt on
        # /load and /clear. It both converses and delegates to skills via run_skill.
        from .memgpt_runtime import build_chat_orchestrator
        self.memgpt = build_chat_orchestrator(project, store)

    @property
    def display_name(self) -> str:
        return self.project.project_name or self.project.name


# ─── Command registry ─────────────────────────────────────────────────────────

class CommandRegistry:
    def __init__(self):
        self._cmds: dict[str, tuple] = {}

    def register(self, *names: str, usage: str = "", description: str = ""):
        def decorator(fn):
            for name in names:
                self._cmds[name] = (fn, usage, description)
            return fn
        return decorator

    def __contains__(self, cmd: str) -> bool:
        return cmd in self._cmds

    def help_lines(self) -> list[tuple[str, str]]:
        seen, result = set(), []
        for name, (fn, usage, desc) in self._cmds.items():
            if fn not in seen:
                seen.add(fn)
                result.append((f"{name} {usage}".strip(), desc))
        return result

    async def dispatch(self, state: REPLState, cmd: str, args: list[str]) -> str | None:
        fn, _, _ = self._cmds[cmd]
        return await fn(state, args)


_registry = CommandRegistry()


# ─── Command handlers ─────────────────────────────────────────────────────────

@_registry.register("/help", "/h", description="Show this help message")
async def cmd_help(_state: REPLState, _args: list[str]) -> None:
    T.console.print(f"\n[cyan]{_('available_commands')}[/cyan]")
    for display, desc in _registry.help_lines():
        T.console.print(f"  [green]{display:<28}[/green] {desc}")
    T.console.print()


@_registry.register("/clear", description="Clear project memory and history")
async def cmd_clear(state: REPLState, _args: list[str]) -> None:
    if await T.aconfirm("Are you sure you want to clear this project's memory?"):
        state.project = state.store.overwrite(
            state.project.name, state.project.mode, state.project.model,
            state.project.project_name, state.project.project_path,
            state.project.skills, state.project.description,
            alternative_model=state.project.alternative_model,
        )
        from .memgpt_runtime import build_chat_orchestrator
        state.memgpt = build_chat_orchestrator(state.project, state.store)
        T.success("Project memory cleared.")


@_registry.register("/rename", usage="<new_name>", description="Rename the current project")
async def cmd_rename(state: REPLState, args: list[str]) -> str | None:
    if not args:
        T.error("Usage: /rename <new_name>")
        return "continue"
    new_name = args[0].strip('"\'')
    if state.store.rename(state.project.name, new_name):
        state.project.name = new_name
        state.store.save(state.project)
        T.success(f"Project renamed to '{new_name}'.")
    else:
        T.error(f"A project named '{new_name}' already exists.")


@_registry.register("/list", description="List all projects")
async def cmd_list(state: REPLState, _args: list[str]) -> None:
    projects = state.store.list_projects()
    if not projects:
        T.info("No projects found.")
    else:
        T.console.print(f"\n[dim]Existing projects:[/dim]")
        for p in projects:
            pname = p["project_name"] or p["name"]
            T.console.print(
                f"  [cyan]{_escape(p['name'])}[/cyan]  "
                f"[bold]{_escape(pname)}[/bold]  "
                f"[dim]{_escape(p['project_path'])}  {p['updated_at'][:10]}  mode={p['mode']}[/dim]"
            )
        T.console.print()


@_registry.register("/load", usage="<name>", description="Load another project")
async def cmd_load(state: REPLState, args: list[str]) -> str | None:
    from .tools import set_project_context
    if not args:
        T.error("Usage: /load <name>")
        return "continue"
    name = args[0].strip('"\'')
    if not state.store.exists(name):
        T.error(f"Project '{name}' not found.")
        return "continue"
    loaded = state.store.load(name)
    if loaded:
        state.project = loaded
        set_project_context(state.project, state.store)
        # Rebuild the MemGPT for the newly loaded project (re-scopes file tools and
        # reseeds memory from the loaded project's history).
        from .memgpt_runtime import build_chat_orchestrator
        state.memgpt = build_chat_orchestrator(state.project, state.store)
        T.success(f"Project '{name}' loaded.")
        T.console.print(f"  [dim]Skills: {', '.join(state.project.skills)}[/dim]")
        if state.project.request and state.project.plan_text and not state.project.results:
            T.warning(_("pending_demand", request=state.project.request[:50]))
    else:
        T.error(f"Project '{name}' not found.")


@_registry.register("/delete", usage="<name>", description="Delete a project")
async def cmd_delete(state: REPLState, args: list[str]) -> str | None:
    if not args:
        T.error("Usage: /delete <name>")
        return "continue"
    name = args[0].strip('"\'')
    if not state.store.exists(name):
        T.error(f"Project '{name}' not found.")
        return "continue"
    
    project_to_delete = state.store.load(name)
    state.store.delete(name)

    import os
    import shutil
    if project_to_delete and project_to_delete.project_path and os.path.exists(project_to_delete.project_path):
        if await T.aconfirm(_("delete_dir_confirm", path=project_to_delete.project_path), default=False):
            try:
                shutil.rmtree(project_to_delete.project_path)
                T.success(_("dir_deleted", path=project_to_delete.project_path))
            except Exception as e:
                T.error(_("dir_delete_failed", err=str(e)))
        else:
            opalacoder_dir = os.path.join(project_to_delete.project_path, ".opalacoder")
            if os.path.exists(opalacoder_dir):
                try:
                    shutil.rmtree(opalacoder_dir)
                    T.success(_("vcs_deleted"))
                except Exception as e:
                    T.error(_("vcs_delete_failed", err=str(e)))

    T.success(f"Project '{name}' deleted.")
    if state.project.name == name:
        T.info("Current project was deleted. Please restart OpalaCoder.")
        return "break"


def _rebuild_memgpt(state: REPLState) -> None:
    """Rebuild the MemGPT so a skills.yaml change takes effect immediately."""
    from .memgpt_runtime import build_chat_orchestrator
    state.memgpt = build_chat_orchestrator(state.project, state.store)


@_registry.register("/lsskills", description="List active skills for this project")
async def cmd_lsskills(state: REPLState, _args: list[str]) -> None:
    from .skills import active_skills
    T.console.print(f"\n[dim]Active skills for this project:[/dim]")
    for s in active_skills(state.project.project_path):
        T.console.print(f"  [cyan]{s['name']}[/cyan]  [dim]{s['description']}[/dim]")
    T.console.print()


@_registry.register("/skills", description="List all available skills (active marked with *)")
async def cmd_skills(state: REPLState, _args: list[str]) -> None:
    from .skills import discover_skills, active_skills
    discovered = discover_skills(state.project.project_path)
    active_names = {s["name"] for s in active_skills(state.project.project_path)}
    if not discovered:
        T.info("No skills found.")
        return
    T.console.print(f"\n[dim]Available skills:[/dim]")
    for s in discovered:
        mark = "[green]*[/green] " if s["name"] in active_names else "  "
        T.console.print(f"  {mark}[cyan]{s['name']}[/cyan]  [dim]{s['description']}[/dim]")
    T.console.print(f"\n[dim]([green]*[/green] = active in this project)[/dim]\n")


@_registry.register("/addskill", usage="<name>", description="Add a skill to this project")
async def cmd_addskill(state: REPLState, args: list[str]) -> str | None:
    from .skills import add_skill_to_project
    if not args:
        T.error("Usage: /addskill <skill_name>")
        return "continue"
    skill_name = args[0].strip().lower()
    changed, msg = add_skill_to_project(state.project.project_path, skill_name)
    if changed:
        _rebuild_memgpt(state)
        T.success(msg)
    else:
        T.info(msg)


@_registry.register("/rmskill", usage="<name>", description="Remove a skill from this project")
async def cmd_rmskill(state: REPLState, args: list[str]) -> str | None:
    from .skills import remove_skill_from_project
    if not args:
        T.error("Usage: /rmskill <skill_name>")
        return "continue"
    skill_name = args[0].strip().lower()
    changed, msg = remove_skill_from_project(state.project.project_path, skill_name)
    if changed:
        _rebuild_memgpt(state)
        T.success(msg)
    else:
        T.info(msg)


# ─── Model commands ───────────────────────────────────────────────────────────

@_registry.register("/models", description="Show the models in use for this project")
async def cmd_models(state: REPLState, _args: list[str]) -> None:
    from .config import DEFAULT_MODEL, ALTERNATIVE_MODEL
    main_model = state.project.model or DEFAULT_MODEL
    alt_model = state.project.alternative_model or ALTERNATIVE_MODEL
    alt_origin = "project" if state.project.alternative_model else "global (agents.yaml)"
    T.console.print(f"\n[dim]Models for project '{state.display_name}':[/dim]")
    T.console.print(f"  [cyan]main[/cyan]        {main_model}")
    T.console.print(f"  [cyan]alternative[/cyan] {alt_model}  [dim]({alt_origin})[/dim]")
    params = getattr(state.project, "model_params", {})
    if params:
        T.console.print(f"  [cyan]parameters[/cyan]")
        for k, v in params.items():
            T.console.print(f"    {k}: {v}")
    T.console.print(f"\n[dim]Change with /set-main-model <id>, /set-alternative-model <id>, or /set-model-param <name> <value>.[/dim]\n")


@_registry.register("/set-main-model", usage="<model_id>",
                    description="Set the main model for this project")
async def cmd_set_main_model(state: REPLState, args: list[str]) -> str | None:
    if not args:
        T.error("Usage: /set-main-model <model_id>  (e.g. ollama/gemma4:latest)")
        return "continue"
    model_id = args[0].strip()
    state.project.model = model_id
    state.store.save(state.project)
    _rebuild_memgpt(state)
    T.success(f"Main model set to '{model_id}' for this project.")


@_registry.register("/set-alternative-model", usage="<model_id>",
                    description="Set the alternative model for this project")
async def cmd_set_alternative_model(state: REPLState, args: list[str]) -> str | None:
    if not args:
        T.error("Usage: /set-alternative-model <model_id>  (e.g. gemini/gemini-2.0-flash)")
        return "continue"
    model_id = args[0].strip()
    state.project.alternative_model = model_id
    state.store.save(state.project)
    _rebuild_memgpt(state)
    T.success(f"Alternative model set to '{model_id}' for this project.")


@_registry.register("/set-model-param", usage="<param_name> <value>",
                    description="Set advanced model parameter (temperature, max_tokens, num_ctx, top_p, frequency_penalty, presence_penalty)")
async def cmd_set_model_param(state: REPLState, args: list[str]) -> str | None:
    if len(args) < 2:
        T.error("Usage: /set-model-param <param_name> <value>\n"
                "Allowed params: temperature, max_tokens, num_ctx, top_p, frequency_penalty, presence_penalty")
        return "continue"
    
    param = args[0].strip().lower()
    val_str = args[1].strip()
    
    allowed_params = {"temperature", "max_tokens", "num_ctx", "top_p", "frequency_penalty", "presence_penalty"}
    if param not in allowed_params:
        T.error(f"Unknown parameter '{param}'. Allowed parameters: {', '.join(allowed_params)}")
        return "continue"
        
    try:
        if param in {"max_tokens", "num_ctx"}:
            val = int(val_str)
            if val <= 0:
                raise ValueError("Must be a positive integer")
        elif param == "temperature":
            val = float(val_str)
            if not (0.0 <= val <= 2.0):
                raise ValueError("Must be between 0.0 and 2.0")
        elif param == "top_p":
            val = float(val_str)
            if not (0.0 <= val <= 1.0):
                raise ValueError("Must be between 0.0 and 1.0")
        elif param in {"frequency_penalty", "presence_penalty"}:
            val = float(val_str)
            if not (-2.0 <= val <= 2.0):
                raise ValueError("Must be between -2.0 and 2.0")
    except ValueError as e:
        T.error(f"Invalid value for '{param}': {e}")
        return "continue"

    if not hasattr(state.project, "model_params") or state.project.model_params is None:
        state.project.model_params = {}
    
    state.project.model_params[param] = val
    state.store.save(state.project)
    _rebuild_memgpt(state)
    T.success(f"Model parameter '{param}' set to {val} for this project.")


@_registry.register("/undo", description=_("undo_desc"))
async def cmd_undo(state: REPLState, _args: list[str]) -> str | None:
    from .vcs import get_vcs_strategy
    from .config import get_git_strategy
    vcs = get_vcs_strategy(get_git_strategy(), state.project.project_path)
    success, msg = vcs.undo_last()
    if success:
        T.success(_("undo_success"))
    else:
        T.error(_("undo_fail") + f" ({msg})")
    return "continue"


@_registry.register("/commit", usage="<message>", description=_("commit_desc"))
async def cmd_commit(state: REPLState, args: list[str]) -> str | None:
    if not args:
        T.error("Usage: /commit <message>")
        return "continue"
    message = " ".join(args).strip('"\'')
    from .vcs import get_vcs_strategy
    from .config import get_git_strategy
    vcs = get_vcs_strategy(get_git_strategy(), state.project.project_path)
    success, msg = vcs.manual_commit(message)
    if success:
        T.success(_("commit_success"))
    else:
        T.error(_("commit_fail", err=msg))
    return "continue"


@_registry.register("/exit", "/quit", description=_("exit_desc"))
async def cmd_exit(_state: REPLState, _args: list[str]) -> str:
    T.info(_("exiting"))
    return "break"
