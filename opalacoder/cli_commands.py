"""REPL command registry and handlers for OpalaCoder CLI."""

from .project import ProjectStore, ProjectData
from .agents import make_chat_memgpt_agent
from . import terminal as T
from .i18n import _
from rich.markup import escape as _escape


# ─── REPL state container ─────────────────────────────────────────────────────

class REPLState:
    def __init__(self, project: ProjectData, store: ProjectStore, project_skills: list, chat_agent):
        self.project = project
        self.store = store
        self.project_skills = project_skills
        self.chat_agent = chat_agent

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
    from .skills import load_project_skills
    if T.confirm("Are you sure you want to clear this project's memory?"):
        state.project = state.store.overwrite(
            state.project.name, state.project.mode, state.project.model,
            state.project.project_name, state.project.project_path,
            state.project.skills, state.project.description,
        )
        state.project_skills = load_project_skills(state.project.project_path, state.project.skills)
        state.chat_agent = make_chat_memgpt_agent(state.project.model)
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
    from .skills import load_project_skills
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
        state.project_skills = load_project_skills(state.project.project_path, state.project.skills)
        state.chat_agent = make_chat_memgpt_agent(state.project.model)
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
        if T.confirm(_("delete_dir_confirm", path=project_to_delete.project_path), default=False):
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


@_registry.register("/lsskills", description="List active skills for this project")
async def cmd_lsskills(state: REPLState, _args: list[str]) -> None:
    T.console.print(f"\n[dim]Active skills for this project:[/dim]")
    for s in state.project_skills:
        T.console.print(f"  [cyan]{s['name']}[/cyan]  [dim]{s['description']}[/dim]")
    T.console.print()


@_registry.register("/skills", description="List all available skills (active marked with *)")
async def cmd_skills(state: REPLState, _args: list[str]) -> None:
    from .skills import _skill_search_dirs, _parse_skill_file
    import os as _os
    search_dirs = _skill_search_dirs(state.project.project_path)
    found_any = False
    for s_dir in search_dirs:
        if not _os.path.isdir(s_dir):
            continue
        files = sorted(f for f in _os.listdir(s_dir) if f.endswith(".md"))
        if not files:
            continue
        T.console.print(f"\n[dim]Skills in [bold]{_escape(s_dir)}[/bold]:[/dim]")
        for filename in files:
            skill = _parse_skill_file(_os.path.join(s_dir, filename))
            if skill:
                active = "[green]*[/green] " if skill["name"] in state.project.skills else "  "
                T.console.print(f"  {active}[cyan]{skill['name']}[/cyan]  [dim]{skill['description']}[/dim]")
        found_any = True
    if not found_any:
        T.info("No skill files found.")
    T.console.print(f"\n[dim]([green]*[/green] = active in this project)[/dim]\n")


@_registry.register("/addskill", usage="<name>", description="Add a skill to this project")
async def cmd_addskill(state: REPLState, args: list[str]) -> str | None:
    from .skills import find_skill_file, load_project_skills
    if not args:
        T.error("Usage: /addskill <skill_name>")
        return "continue"
    skill_name = args[0].strip().lower()
    if skill_name in state.project.skills:
        T.info(f"Skill '{skill_name}' is already active.")
        return "continue"
    found = find_skill_file(skill_name, state.project.project_path)
    if not found:
        T.error(f"Skill '{skill_name}.md' not found in any skills directory.")
    else:
        state.project.skills.append(skill_name)
        state.store.save(state.project)
        state.project_skills = load_project_skills(state.project.project_path, state.project.skills)
        T.success(f"Skill '{skill_name}' added to project.")


@_registry.register("/rmskill", usage="<name>", description="Remove a skill from this project")
async def cmd_rmskill(state: REPLState, args: list[str]) -> str | None:
    from .skills import load_project_skills
    if not args:
        T.error("Usage: /rmskill <skill_name>")
        return "continue"
    skill_name = args[0].strip().lower()
    if skill_name == "opalacoder":
        T.error("Skill 'opalacoder' is required and cannot be removed.")
        return "continue"
    if skill_name not in state.project.skills:
        T.info(f"Skill '{skill_name}' is not active in this project.")
        return "continue"
    state.project.skills.remove(skill_name)
    state.store.save(state.project)
    state.project_skills = load_project_skills(state.project.project_path, state.project.skills)
    T.success(f"Skill '{skill_name}' removed from project.")


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
