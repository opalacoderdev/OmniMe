"""OpalaCoder CLI – entry point."""

import asyncio
import argparse
import os
import sys

from . import __version__
from .config import DEFAULT_MODEL, ALTERNATIVE_MODEL, DEFAULT_MAX_RETRIES, DEFAULT_MODE, DEFAULT_DB_PATH, DEFAULT_LANG
from .project import ProjectStore, ProjectData
from .agents import make_chat_memgpt_agent, enricher_system_prompt, synthesizer_system_prompt
from .api_keys import ensure_api_key
from . import terminal as T
from agenticblocks.blocks.llm.agent import AgentInput
from .i18n import _, set_lang
from rich.markup import escape as _escape
from .cli_commands import REPLState, _registry
from .orchestrator import CHECKPOINT_SUBPATH


def _inject_project(project: ProjectData, prompt: str) -> str:
    """Prepend project context to every prompt sent to agents."""
    return project.context_header() + prompt


async def _synthesize_and_respond(state, store, orchestrator_result: str) -> None:
    """Pass orchestrator result to MemGPT for memory storage and user-facing synthesis.

    MemGPT is the only agent that speaks to the user. After an orchestrator finishes,
    it receives the raw result, stores important facts in long-term memory (via its
    append_core_memory tool), and produces a clear summary for the user.
    """
    T.section(_("phase5"))

    if not orchestrator_result or not orchestrator_result.strip():
        orchestrator_result = "(Orchestrator completed without output.)"

    synthesis_prompt = (
        f"[ORCHESTRATOR RESULT]\n{orchestrator_result}\n[END RESULT]\n\n"
        "The orchestrator has finished executing. You MUST:\n"
        "1. Use `append_core_memory` to save any important new facts "
        "(files created/modified, patterns established, decisions made).\n"
        "2. Call `send_message` with a concise, user-friendly summary of what was accomplished."
    )

    # Switch to Mode B — synthesizer speaks to the user
    state.chat_agent.system_prompt = synthesizer_system_prompt()
    with T.spinner(_("agent_thinking")):
        synthesis_obj = await state.chat_agent.run(AgentInput(prompt=synthesis_prompt))
        user_response = synthesis_obj.response.strip() if synthesis_obj.response else orchestrator_result

    T.console.print(f"\n[bold green]OpalaCoder:[/bold green] {user_response}\n")
    store.append_message(state.project, "assistant", user_response)
    store.save(state.project)


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
    from .tools import set_project_context
    from .skills import load_project_skills

    set_project_context(project, store)
    project_skills = load_project_skills(project.project_path, project.skills)

    T.section(f"Active Project: {_escape(project.project_name or project.name)}")
    T.console.print(f"  [dim]Path:   {_escape(project.project_path)}[/dim]")
    T.console.print(f"  [dim]Skills: {', '.join(project.skills)}[/dim]")

    chat_agent = make_chat_memgpt_agent(project.model)
    _VALID_ROLES = {"user", "assistant", "system", "tool"}
    if hasattr(chat_agent, "internal_history") and project.history:
        for msg in project.history[-10:]:
            role = msg["role"]
            content = msg["content"]
            if role not in _VALID_ROLES:
                # Remap orchestration log roles to assistant so LiteLLM accepts them
                # but the content (plan/task summaries) is still visible to the chat agent.
                role = "assistant"
            chat_agent.internal_history.append({"role": role, "content": content})

    state = REPLState(project, store, project_skills, chat_agent)

    if state.project.request and state.project.plan_text and not state.project.results:
        T.warning(_("pending_demand", request=state.project.request[:50]))
        choice = T.choose(_("resume_or_clear"), [_("resume"), _("clear")])
        if choice == _("resume"):
            result = await run_pipeline(state.project, store, max_retries, project_skills=state.project_skills)
            await _synthesize_and_respond(state, store, result)
        else:
            state.project.clear_state()
            store.save(state.project)
    else:
        checkpoint_path = os.path.join(project.project_path, CHECKPOINT_SUBPATH)
        if os.path.exists(checkpoint_path):
            T.warning("[yellow]Foi detectada uma execução de agente não finalizada (checkpoint salvo).[/yellow]")
            choice = T.choose(_("resume_or_clear"), [_("resume"), _("clear")])
            if choice == _("resume"):
                result = await run_pipeline(state.project, store, max_retries, request="[RESUME_EXECUTION]", project_skills=state.project_skills)
                await _synthesize_and_respond(state, store, result)
            else:
                try:
                    os.remove(checkpoint_path)
                except Exception:
                    pass

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
                _VALID_INTENTS = {"greetings", "question", "plan", "resume", "chat", "command_hint"}
                
                # 1. Enricher: chat agent in Mode A — retrieves memory and enriches the user message.
                #    Output goes to the classifier, NOT to the user.
                state.chat_agent.system_prompt = enricher_system_prompt()
                with T.spinner(_("agent_thinking")):
                    enriched_obj = await state.chat_agent.run(AgentInput(prompt=_inject_project(state.project, user_input)))
                    enriched_output = enriched_obj.response.strip() if enriched_obj.response else user_input

                # 2. Classifier receives original message + enriched context
                classifier_prompt = f"USER REQUEST: {user_input}\nENRICHED CONTEXT: {enriched_output}"
                with T.spinner(_("classifying_intent")):
                    intent_res = await state.intent_classifier.run(AgentInput(prompt=classifier_prompt))
                    _raw = intent_res.response.strip().lower()
                    intent = _raw.split()[0].strip(".,!?*\"'") if _raw else ""

                if not intent or intent not in _VALID_INTENTS:
                    T.console.print(f"[yellow]{_('intent_unclear')}[/yellow]")
                    continue

                if intent == "command_hint":
                    cmd_word = user_input.strip().split()[0].lower()
                    T.console.print(f"[yellow]{_('command_hint_suggestion', cmd=cmd_word)}[/yellow]")
                    continue

                # 3. Conversation intents — switch to synthesizer mode so the agent speaks to the user.
                if intent in ("greetings", "question", "chat"):
                    state.chat_agent.system_prompt = synthesizer_system_prompt()
                    with T.spinner(_("agent_thinking")):
                        chat_resp_obj = await state.chat_agent.run(AgentInput(prompt=_inject_project(state.project, user_input)))
                        chat_output = chat_resp_obj.response.strip() if chat_resp_obj.response else enriched_output
                    T.console.print(f"\n[bold green]OpalaCoder:[/bold green] {chat_output}\n")
                    store.append_message(state.project, "user", user_input)
                    store.append_message(state.project, "assistant", chat_output)
                    continue

                # 4. Plan / resume — enriched_output carries memory context for the orchestrator.
                #    User input is saved; enriched_output goes to orchestrator as context only.
                store.append_message(state.project, "user", user_input)

                if intent == "resume":
                    if state.project.request:
                        T.info("Retomando a execução do plano anterior...")
                        resume_request = "[RESUME_EXECUTION]"
                    else:
                        # No in-memory request: use enriched memory context to reconstruct what to do.
                        # The enricher already retrieved relevant past work from archival memory.
                        T.info("Retomando com base no contexto de memória...")
                        resume_request = (
                            f"Original Request: {user_input}\n"
                            f"Memory Context (from chat agent):\n{enriched_output}\n\n"
                            "Based on the memory context above, continue or complete the previous implementation."
                        )
                    try:
                        orchestrator_result = await run_pipeline(
                            state.project, store, max_retries,
                            request=resume_request,
                            active_model=state.project.model,
                            project_skills=state.project_skills,
                        )
                        await _synthesize_and_respond(state, store, orchestrator_result)
                    except Exception as e:
                        T.error(f"Erro ao retomar plano: {e}")
                    continue

                if intent == "plan":
                    if state.project.results or state.project.request:
                        state.project.clear_state()
                        store.save(state.project)

                    if state.project.model.startswith("ollama/"):
                        complexity = "alternative" if len(user_input.split()) > 200 else "default"
                    else:
                        with T.spinner(_("evaluating_complexity")):
                            comp_res = await state.complexity_evaluator.run(AgentInput(prompt=user_input))
                            raw_comp = comp_res.response.strip().lower()
                            complexity = "alternative" if "alternative" in raw_comp else "default"

                    if complexity == "alternative":
                        if ensure_api_key(ALTERNATIVE_MODEL):
                            T.info(_("routing_complex_task", model=ALTERNATIVE_MODEL))
                            active_model = ALTERNATIVE_MODEL
                        else:
                            T.warning(_("api_key_missing_fallback", model=state.project.model))
                            active_model = state.project.model
                    else:
                        active_model = state.project.model

                    # enriched_output carries memory context from the enricher for the orchestrator
                    augmented_request = (
                        f"Original Request: {user_input}\n"
                        f"Memory Context (from chat agent):\n{enriched_output}"
                    )

                    try:
                        orchestrator_result = await run_pipeline(
                            state.project, store, max_retries,
                            request=augmented_request,
                            active_model=active_model,
                            project_skills=state.project_skills,
                        )
                        await _synthesize_and_respond(state, store, orchestrator_result)
                    except Exception as e:
                        if active_model != state.project.model:
                            T.error(_("alt_model_error", model=active_model, err=e))
                            T.info(_("fallback_to_model", model=state.project.model))
                            if state.project.results or state.project.request:
                                state.project.clear_state()
                                store.save(state.project)
                            orchestrator_result = await run_pipeline(
                                state.project, store, max_retries,
                                request=augmented_request,
                                active_model=state.project.model,
                                project_skills=state.project_skills,
                            )
                            await _synthesize_and_respond(state, store, orchestrator_result)
                        else:
                            raise

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
) -> str:
    model = active_model or project.model
    T.info(_("using_model", model=model))

    if not request:
        return ""

    T.section(_("new_demand"))
    store.append_message(project, "user", request)
    project.request = request
    store.save(project)

    _VALID_ROLES = {"user", "assistant", "system", "tool"}
    hist_text = ""
    for msg in project.history[-10:-1]:
        if msg["role"] == "user":
            hist_text += f"User: {msg['content']}\n"
        elif msg["role"] in _VALID_ROLES or msg["role"].startswith("system_"):
            hist_text += f"Assistant: {msg['content']}\n"

    from .orchestrator import get_orchestrator
    from .config import get_agent_strategy
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

    from .profiles import load_profiles, resolve_profile
    from .profile_executor import ProfileExecutorStrategy

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    global_profiles = load_profiles(os.path.join(repo_root, "profiles"))

    local_profiles = {}
    if hasattr(project, "project_path") and project.project_path:
        local_profiles = load_profiles(os.path.join(project.project_path, "profiles"))

    profiles = {**global_profiles, **local_profiles}
    selected_profile = await resolve_profile(request, profiles, model)

    if selected_profile and selected_profile in profiles:
        T.section(_("execution_profile_selected"))
        T.info(f"Profile: {selected_profile}")
        orchestrator = ProfileExecutorStrategy(model=model, profile_data=profiles[selected_profile])
    else:
        strategy_name = get_agent_strategy("orchestrator")
        orchestrator = get_orchestrator(strategy_name, model)

    final_response = await orchestrator.run(
        user_request=enriched_request,
        history=hist_text,
        session=project,
        store=store,
        max_retries=max_retries,
    )

    # Save raw orchestrator output to archival (subconscious record)
    store.append_message(project, "assistant", final_response)

    project.clear_state()
    store.save(project)
    return final_response


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
