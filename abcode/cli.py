"""ABCode CLI – entry point."""

import asyncio
import argparse
import os
import sys

from . import __version__
from .config import DEFAULT_MODEL, ALTERNATIVE_MODEL, DEFAULT_MAX_RETRIES, DEFAULT_MODE, DEFAULT_DB_PATH, DEFAULT_LANG
from .project import ProjectStore, ProjectData
from .planner import generate_panorama, refine_plan, decompose_plan
from .executor import execute_subplans, aggregate_results
from .subplan import Subplan
from .agents import make_chat_memgpt_agent, make_intent_classifier, make_complexity_evaluator
from .api_keys import ensure_api_key
from . import terminal as T
from agenticblocks.blocks.llm.agent import AgentInput
from .i18n import _, set_lang
from rich.markup import escape as _escape


def _inject_project(project: ProjectData, prompt: str) -> str:
    """Prepend project context to every prompt sent to agents."""
    return project.context_header() + prompt


# ─── Project startup menu ─────────────────────────────────────────────────────

async def startup_menu(store: ProjectStore, args) -> ProjectData:
    """Show the project selection/creation menu and return a ready ProjectData."""
    projects = store.list_projects()

    if projects:
        options = ["Create new project"] + [
            f"{p['project_name'] or p['name']}  [{p['project_path']}]"
            for p in projects
        ]
        choice = T.choose("What would you like to do?", options[:4] if len(options) > 4 else options)
        # If more than 3 existing projects, show full list via /list
        if choice == "Create new project":
            return await _create_project(store, args)
        else:
            # Match back to project record
            idx = options.index(choice) - 1
            name = projects[idx]["name"]
            project = store.load(name)
            project.mode = args.mode
            project.model = args.model
            store.save(project)
            T.success(f"Project '{project.project_name or project.name}' loaded.")
            return project
    else:
        T.info("No projects found. Let's create your first one.")
        return await _create_project(store, args)


async def _create_project(store: ProjectStore, args) -> ProjectData:
    """Interactively create a new project and select its skills via LLM."""
    from .skills import select_skills_for_project, load_skills

    project_name = T.ask("Project name").strip() or "default"
    cwd = os.getcwd()
    entered_path = T.ask(f"Project path [{cwd}]").strip()
    project_path = os.path.abspath(entered_path if entered_path else cwd)

    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
        T.success(f"Directory created: {project_path}")

    description = T.ask("Brief project description (used to select skills)").strip()

    # Always show which skills exist before LLM selection
    all_skills = load_skills(project_path)
    available = [s["name"] for s in all_skills if s["name"] != "abcode"]
    T.info(f"Available skills: abcode (default), {', '.join(available) if available else '(none)'}")

    if description and available:
        with T.spinner("Selecting skills for this project..."):
            chosen_skills = await select_skills_for_project(args.model, description, project_path)
    else:
        chosen_skills = ["abcode"]

    T.success(f"Skills selected: {', '.join(chosen_skills)}")

    db_key = project_name.replace(" ", "_").lower()
    # Handle name collision
    if store.exists(db_key):
        db_key = db_key + "_1"

    project = store.create(
        name=db_key,
        mode=args.mode,
        model=args.model,
        project_name=project_name,
        project_path=project_path,
        skills=chosen_skills,
        description=description,
    )
    T.success(f"Project '{project_name}' created.")
    return project


# ─── REPL Loop ────────────────────────────────────────────────────────────────

async def repl_loop(project: ProjectData, store: ProjectStore, max_retries: int) -> None:
    from .tools import set_project_path
    from .skills import load_project_skills

    set_project_path(project.project_path)

    # Load only project-scoped skills once — reused for all prompts in this session.
    project_skills = load_project_skills(project.project_path, project.skills)

    display_name = project.project_name or project.name
    T.section(f"Active Project: {_escape(display_name)}")
    T.console.print(f"  [dim]Path:   {_escape(project.project_path)}[/dim]")
    T.console.print(f"  [dim]Skills: {', '.join(project.skills)}[/dim]")

    chat_agent = make_chat_memgpt_agent(project.model)

    if project.request and project.plan_text and not project.results:
        T.warning(_("pending_demand", request=project.request[:50]))
        choice = T.choose(_("resume_or_clear"), [_("resume"), _("clear")])
        if choice == _("resume"):
            await run_pipeline(project, store, max_retries, project_skills=project_skills)
        else:
            project.clear_state()
            store.save(project)

    while True:
        try:
            user_input = T.ask(f"ABCode ({display_name})")
            if not user_input:
                continue

            if user_input.startswith("/"):
                cmd, *args = user_input.split(maxsplit=1)

                if cmd in ("/help", "/h"):
                    T.console.print(f"\n[cyan]{_('available_commands')}[/cyan]")
                    T.console.print(f"  [green]/help[/green]               {_('help_desc')}")
                    T.console.print(f"  [green]/clear[/green]              Clear project memory and history")
                    T.console.print(f"  [green]/rename <name>[/green]      Rename the current project")
                    T.console.print(f"  [green]/list[/green]               List all projects")
                    T.console.print(f"  [green]/load <name>[/green]        Load another project")
                    T.console.print(f"  [green]/delete <name>[/green]      Delete a project")
                    T.console.print(f"  [green]/skills[/green]             List all available skills (active marked with *)")
                    T.console.print(f"  [green]/lsskills[/green]           List active skills for this project")
                    T.console.print(f"  [green]/addskill <name>[/green]    Add a skill to this project")
                    T.console.print(f"  [green]/rmskill <name>[/green]     Remove a skill from this project")
                    T.console.print(f"  [green]/exit[/green]               {_('exit_desc')}\n")

                elif cmd == "/clear":
                    if T.confirm("Are you sure you want to clear this project's memory?"):
                        project = store.overwrite(
                            project.name, project.mode, project.model,
                            project.project_name, project.project_path,
                            project.skills, project.description,
                        )
                        project_skills = load_project_skills(project.project_path, project.skills)
                        chat_agent = make_chat_memgpt_agent(project.model)
                        T.success("Project memory cleared.")

                elif cmd == "/rename":
                    if not args:
                        T.error("Usage: /rename <new_name>")
                        continue
                    new_name = args[0].strip('"\'')
                    if store.rename(project.name, new_name):
                        project.name = new_name
                        store.save(project)
                        T.success(f"Project renamed to '{new_name}'.")
                    else:
                        T.error(f"A project named '{new_name}' already exists.")

                elif cmd == "/list":
                    projects = store.list_projects()
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

                elif cmd == "/load":
                    if not args:
                        T.error("Usage: /load <name>")
                        continue
                    name = args[0].strip('"\'')
                    if not store.exists(name):
                        T.error(f"Project '{name}' not found.")
                        continue
                    loaded = store.load(name)
                    if loaded:
                        project = loaded
                        display_name = project.project_name or project.name
                        set_project_path(project.project_path)
                        project_skills = load_project_skills(project.project_path, project.skills)
                        chat_agent = make_chat_memgpt_agent(project.model)
                        T.success(f"Project '{name}' loaded.")
                        T.console.print(f"  [dim]Skills: {', '.join(project.skills)}[/dim]")
                        if project.request and project.plan_text and not project.results:
                            T.warning(_("pending_demand", request=project.request[:50]))
                    else:
                        T.error(f"Project '{name}' not found.")

                elif cmd == "/delete":
                    if not args:
                        T.error("Usage: /delete <name>")
                        continue
                    name = args[0].strip('"\'')
                    if not store.exists(name):
                        T.error(f"Project '{name}' not found.")
                        continue
                    store.delete(name)
                    T.success(f"Project '{name}' deleted.")
                    if project.name == name:
                        T.info("Current project was deleted. Please restart ABCode.")
                        break

                elif cmd == "/lsskills":
                    T.console.print(f"\n[dim]Active skills for this project:[/dim]")
                    for s in project_skills:
                        T.console.print(f"  [cyan]{s['name']}[/cyan]  [dim]{s['description']}[/dim]")
                    T.console.print()

                elif cmd == "/skills":
                    from .skills import _skill_search_dirs, _parse_skill_file
                    import os as _os
                    search_dirs = _skill_search_dirs(project.project_path)
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
                                active = "[green]*[/green] " if skill["name"] in project.skills else "  "
                                T.console.print(f"  {active}[cyan]{skill['name']}[/cyan]  [dim]{skill['description']}[/dim]")
                        found_any = True
                    if not found_any:
                        T.info("No skill files found.")
                    T.console.print(f"\n[dim]([green]*[/green] = active in this project)[/dim]\n")

                elif cmd == "/addskill":
                    if not args:
                        T.error("Usage: /addskill <skill_name>")
                        continue
                    skill_name = args[0].strip().lower()
                    if skill_name in project.skills:
                        T.info(f"Skill '{skill_name}' is already active.")
                        continue
                    from .skills import find_skill_file
                    found = find_skill_file(skill_name, project.project_path)
                    if not found:
                        T.error(f"Skill '{skill_name}.md' not found in any skills directory.")
                    else:
                        project.skills.append(skill_name)
                        store.save(project)
                        project_skills = load_project_skills(project.project_path, project.skills)
                        T.success(f"Skill '{skill_name}' added to project.")

                elif cmd == "/rmskill":
                    if not args:
                        T.error("Usage: /rmskill <skill_name>")
                        continue
                    skill_name = args[0].strip().lower()
                    if skill_name == "abcode":
                        T.error("Skill 'abcode' is required and cannot be removed.")
                        continue
                    if skill_name not in project.skills:
                        T.info(f"Skill '{skill_name}' is not active in this project.")
                        continue
                    project.skills.remove(skill_name)
                    store.save(project)
                    project_skills = load_project_skills(project.project_path, project.skills)
                    T.success(f"Skill '{skill_name}' removed from project.")

                elif cmd in ("/exit", "/quit"):
                    T.info(_("exiting"))
                    break

                else:
                    T.error(_("unknown_command", cmd=cmd))

            else:
                hist_text = ""
                for msg in project.history[-10:]:
                    role = "Assistant" if msg["role"] == "assistant" else "User"
                    hist_text += f"{role}: {msg['content']}\n"

                base_prompt = _inject_project(project, user_input)
                full_prompt = (
                    f"[CONVERSATION HISTORY]\n{hist_text}\n[END HISTORY]\n\n[USER'S NEW MESSAGE]:\n{base_prompt}"
                    if hist_text else base_prompt
                )

                from .skills import get_relevant_skills_llm, SCOPE_CLASSIFIER

                skills_context_for_intent = await get_relevant_skills_llm(
                    project.model, full_prompt, scope=SCOPE_CLASSIFIER, project_skills=project_skills
                )

                intent_prompt = full_prompt
                if skills_context_for_intent:
                    intent_prompt = f"BACKGROUND CONTEXT / SKILLS:\n{skills_context_for_intent}\n\nUSER MESSAGE TO CLASSIFY:\n{full_prompt}"

                _VALID_INTENTS = {"greetings", "question", "plan", "chat"}
                classifier = make_intent_classifier(project.model)
                with T.spinner(_("agent_thinking")):
                    intent_res = await classifier.run(AgentInput(prompt=intent_prompt))
                    _raw = intent_res.response.strip().lower()
                    intent = _raw.split()[0].rstrip(".,!?") if _raw else "plan"
                    if intent not in _VALID_INTENTS:
                        intent = "plan"

                if intent == "plan":
                    if project.results or project.request:
                        project.clear_state()
                        store.save(project)

                    if project.model.startswith("ollama/"):
                        complexity = "alternative" if len(user_input.split()) > 200 else "default"
                    else:
                        complexity_evaluator = make_complexity_evaluator(project.model)
                        with T.spinner("Evaluating task complexity..."):
                            comp_res = await complexity_evaluator.run(AgentInput(prompt=user_input))
                            complexity = comp_res.response.strip().lower().split()[0]
                            if complexity not in ("default", "alternative"):
                                complexity = "default"

                    if complexity == "alternative":
                        if ensure_api_key(ALTERNATIVE_MODEL):
                            T.info(f"Complex task detected. Routing to alternative model ({ALTERNATIVE_MODEL})...")
                            active_model = ALTERNATIVE_MODEL
                        else:
                            T.warning(f"API Key missing or skipped. Falling back to {project.model}.")
                            active_model = project.model
                    else:
                        active_model = project.model

                    try:
                        await run_pipeline(project, store, max_retries, request=user_input, active_model=active_model, project_skills=project_skills)
                    except Exception as e:
                        if active_model != project.model:
                            T.error(f"Error using alternative model ({active_model}): {e}")
                            T.info(f"Falling back to {project.model}")
                            if project.results or project.request:
                                project.clear_state()
                                store.save(project)
                            await run_pipeline(project, store, max_retries, request=user_input, active_model=project.model, project_skills=project_skills)
                        else:
                            raise
                else:
                    with T.spinner(_("agent_thinking")):
                        response = await chat_agent.run(AgentInput(prompt=_inject_project(project, user_input)))
                    answer = response.response.strip() if response.response else "(no response)"
                    T.console.print(f"\n[bold green]ABCode:[/bold green] {answer}\n")
                    store.append_message(project, "user", user_input)
                    store.append_message(project, "assistant", answer)

        except KeyboardInterrupt:
            T.info(_("repl_interrupted"))
            break
        except EOFError:
            T.info(_("exiting"))
            break
        except T.UserCancelled:
            T.info(_("repl_cancelled"))
            project.clear_state()
            store.save(project)
        except T.AppExit:
            T.info(_("exiting"))
            break
        except Exception as e:
            T.error(_("unexpected_error", err=e))


async def run_pipeline(
    project: ProjectData,
    store: ProjectStore,
    max_retries: int,
    request: str = None,
    active_model: str = None,
    project_skills: list = None,
) -> None:
    model = active_model or project.model

    if not request:
        return

    T.section(_("new_demand"))
    store.append_message(project, "user", request)
    project.request = request
    store.save(project)

    hist_text = ""
    for msg in project.history[-10:-1]:
        role = "Assistant" if msg["role"] == "assistant" else "User"
        hist_text += f"{role}: {msg['content']}\n"

    from .orchestrator import AutonomousOrchestratorStrategy  # noqa: F401 (DeterministicOrchestratorStrategy kept for future use)
    from .skills import get_relevant_skills_llm, SCOPE_ORCHESTRATOR

    orchestrator_skills = await get_relevant_skills_llm(
        model, request, scope=SCOPE_ORCHESTRATOR, project_skills=project_skills
    )
    enriched_request = _inject_project(project, request)
    if orchestrator_skills:
        enriched_request = f"{orchestrator_skills}\n\n[USER REQUEST]:\n{enriched_request}"

    orchestrator = AutonomousOrchestratorStrategy(model=model)

    final_response = await orchestrator.run(
        user_request=enriched_request,
        history=hist_text,
        session=project,
        store=store,
        max_retries=max_retries,
    )

    T.section(_("phase5"))

    store.append_message(project, "assistant", final_response)
    T.show_result(final_response)
    project.clear_state()
    store.save(project)


# ─── CLI entrypoint ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abcode",
        description="ABCode – project-centric coding agent",
    )
    parser.add_argument("--version", action="version", version=f"ABCode {__version__}")
    parser.add_argument("--mode", choices=["auto", "plan", "edit"], default=DEFAULT_MODE)
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--lang", choices=["en", "pt"], default=DEFAULT_LANG)
    parser.add_argument("--delete", metavar="PROJECT_NAME", help="Delete a project and exit")
    parser.add_argument("--list-projects", action="store_true", help="List all projects and exit")
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.debug:
        from abcode.config import setup_litellm_debug
        setup_litellm_debug()

    set_lang(args.lang)
    T.print_banner(version=__version__, mode=args.mode)

    store = ProjectStore(db_path=args.db)

    if args.list_projects:
        projects = store.list_projects()
        if not projects:
            T.info("No projects found.")
        else:
            T.section("Existing Projects")
            for p in projects:
                pname = p["project_name"] or p["name"]
                T.console.print(
                    f"  [cyan]{_escape(p['name'])}[/cyan]  [bold]{_escape(pname)}[/bold]  "
                    f"[dim]{_escape(p['project_path'])}  {p['updated_at'][:10]}[/dim]"
                )
        sys.exit(0)

    if args.delete:
        if store.exists(args.delete):
            store.delete(args.delete)
            T.success(f"Project '{args.delete}' deleted.")
        else:
            T.error(f"Project '{args.delete}' not found.")
        sys.exit(0)

    try:
        project = asyncio.run(startup_menu(store, args))
        asyncio.run(repl_loop(project, store, max_retries=args.max_retries))
    except KeyboardInterrupt:
        T.warning(_("repl_interrupted"))
        sys.exit(0)


if __name__ == "__main__":
    main()
