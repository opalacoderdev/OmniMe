"""OpalaCoder CLI – entry point."""

import asyncio
import argparse
import os
import sys

from . import __version__
from .config import DEFAULT_MODEL, ALTERNATIVE_MODEL, DEFAULT_MAX_RETRIES, DEFAULT_MODE, DEFAULT_DB_PATH, DEFAULT_LANG
from .project import ProjectStore, ProjectData
from .agents import make_chat_memgpt_agent, make_intent_classifier, make_complexity_evaluator
from .api_keys import ensure_api_key
from . import terminal as T
from agenticblocks.blocks.llm.agent import AgentInput
from .i18n import _, set_lang
from rich.markup import escape as _escape
from .cli_commands import REPLState, _registry


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
        if choice == "Create new project":
            return await _create_project(store, args)
        else:
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

    all_skills = load_skills(project_path)
    available = [s["name"] for s in all_skills if s["name"] != "opalacoder"]
    T.info(f"Available skills: opalacoder (default), {', '.join(available) if available else '(none)'}")

    if description and available:
        with T.spinner(_("selecting_skills")):
            chosen_skills = await select_skills_for_project(args.model, description, project_path)
    else:
        chosen_skills = ["opalacoder"]

    T.success(f"Skills selected: {', '.join(chosen_skills)}")

    db_key = project_name.replace(" ", "_").lower()
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
    project_skills = load_project_skills(project.project_path, project.skills)

    T.section(f"Active Project: {_escape(project.project_name or project.name)}")
    T.console.print(f"  [dim]Path:   {_escape(project.project_path)}[/dim]")
    T.console.print(f"  [dim]Skills: {', '.join(project.skills)}[/dim]")

    chat_agent = make_chat_memgpt_agent(project.model)
    state = REPLState(project, store, project_skills, chat_agent)

    if state.project.request and state.project.plan_text and not state.project.results:
        T.warning(_("pending_demand", request=state.project.request[:50]))
        choice = T.choose(_("resume_or_clear"), [_("resume"), _("clear")])
        if choice == _("resume"):
            await run_pipeline(state.project, store, max_retries, project_skills=state.project_skills)
        else:
            state.project.clear_state()
            store.save(state.project)

    while True:
        try:
            user_input = T.ask(f"OpalaCoder ({state.display_name})")
            if not user_input:
                continue

            if user_input.startswith("/"):
                cmd, *args = user_input.split(maxsplit=1)
                if cmd not in _registry:
                    T.error(_("unknown_command", cmd=cmd))
                    continue
                result = await _registry.dispatch(state, cmd, args)
                if result == "break":
                    break
                elif result == "continue":
                    continue

            else:
                _VALID_INTENTS = {"greetings", "question", "plan", "chat", "command_hint"}
                classifier = make_intent_classifier(state.project.model)
                with T.spinner(_("agent_thinking")):
                    intent_res = await classifier.run(AgentInput(prompt=user_input))
                    _raw = intent_res.response.strip().lower()
                    intent = _raw.split()[0].rstrip(".,!?") if _raw else ""


                if not intent or intent not in _VALID_INTENTS:
                    T.console.print(f"[yellow]{_('intent_unclear')}[/yellow]")
                    continue

                if intent == "command_hint":
                    cmd_word = user_input.strip().split()[0].lower()
                    T.console.print(f"[yellow]{_('command_hint_suggestion', cmd=cmd_word)}[/yellow]")
                    continue

                if intent == "plan":
                    if state.project.results or state.project.request:
                        state.project.clear_state()
                        store.save(state.project)

                    if state.project.model.startswith("ollama/"):
                        complexity = "alternative" if len(user_input.split()) > 200 else "default"
                    else:
                        complexity_evaluator = make_complexity_evaluator(state.project.model)
                        with T.spinner(_("evaluating_complexity")):
                            comp_res = await complexity_evaluator.run(AgentInput(prompt=user_input))
                            complexity = comp_res.response.strip().lower().split()[0]
                            if complexity not in ("default", "alternative"):
                                complexity = "default"

                    if complexity == "alternative":
                        if ensure_api_key(ALTERNATIVE_MODEL):
                            T.info(_("routing_complex_task", model=ALTERNATIVE_MODEL))
                            active_model = ALTERNATIVE_MODEL
                        else:
                            T.warning(_("api_key_missing_fallback", model=state.project.model))
                            active_model = state.project.model
                    else:
                        active_model = state.project.model

                    try:
                        await run_pipeline(state.project, store, max_retries, request=user_input, active_model=active_model, project_skills=state.project_skills)
                    except Exception as e:
                        if active_model != state.project.model:
                            T.error(_("alt_model_error", model=active_model, err=e))
                            T.info(_("fallback_to_model", model=state.project.model))
                            if state.project.results or state.project.request:
                                state.project.clear_state()
                                store.save(state.project)
                            await run_pipeline(state.project, store, max_retries, request=user_input, active_model=state.project.model, project_skills=state.project_skills)
                        else:
                            raise
                else:
                    with T.spinner(_("agent_thinking")):
                        response = await state.chat_agent.run(AgentInput(prompt=_inject_project(state.project, user_input)))
                    answer = response.response.strip() if response.response else "(no response)"
                    T.console.print(f"\n[bold green]OpalaCoder:[/bold green] {answer}\n")
                    store.append_message(state.project, "user", user_input)
                    store.append_message(state.project, "assistant", answer)

        except KeyboardInterrupt:
            T.info(_("repl_interrupted"))
            break
        except EOFError:
            T.info(_("exiting"))
            break
        except T.UserCancelled:
            T.info(_("repl_cancelled"))
            state.project.clear_state()
            store.save(state.project)
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

    from .orchestrator import AutonomousOrchestratorStrategy, CodePlanExecutorStrategy
    from .config import get_orchestrator_strategy
    from .skills import get_relevant_skills_llm, SCOPE_ORCHESTRATOR

    orchestrator_skills = await get_relevant_skills_llm(
        model, request, scope=SCOPE_ORCHESTRATOR, project_skills=project_skills
    )
    enriched_request = request
    if orchestrator_skills:
        enriched_request = (
            f"[SKILLS CONTEXT]:\n{orchestrator_skills}\n[END SKILLS CONTEXT]\n\n"
            f"[USER REQUEST]:\n{request}\n[END USER REQUEST]"
        )

    strategy_name = get_orchestrator_strategy()
    if strategy_name == "code_plan":
        orchestrator = CodePlanExecutorStrategy(model=model)
    else:
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
        prog="opalacoder",
        description="OpalaCoder – project-centric coding agent",
    )
    parser.add_argument("--version", action="version", version=f"OpalaCoder {__version__}")
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
        from opalacoder.config import setup_litellm_debug
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
