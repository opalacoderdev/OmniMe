"""ABCode CLI – entry point."""

import asyncio
import argparse
import sys

from . import __version__
from .config import DEFAULT_MODEL, DEFAULT_MAX_RETRIES, DEFAULT_MODE, DEFAULT_DB_PATH, DEFAULT_LANG
from .session import SessionStore, SessionData
from .planner import generate_panorama, refine_plan, decompose_plan
from .executor import execute_subplans, aggregate_results
from .subplan import Subplan
from .agents import make_chat_agent, make_intent_classifier
from . import terminal as T
from agenticblocks.blocks.llm.agent import AgentInput
from .i18n import _, set_lang


# ─── REPL Loop ───────────────────────────────────────────────────────────────

async def repl_loop(session: SessionData, store: SessionStore, max_retries: int) -> None:
    T.section(_("active_session", name=session.name))
    if session.name == "default":
        T.info(_("default_session_warning"))
        T.info(_("type_help"))
        
    if session.request and session.plan_text and not session.results:
        T.warning(_("pending_demand", request=session.request[:50]))
        choice = T.choose(_("resume_or_clear"), [_("resume"), _("clear")])
        if choice == _("resume"):
            await run_pipeline(session, store, max_retries)
        else:
            session.clear_state()
            store.save(session)

    while True:
        try:
            user_input = T.ask(f"ABCode ({session.name})")
            if not user_input:
                continue
                
            if user_input.startswith("/"):
                cmd, *args = user_input.split(maxsplit=1)
                if cmd in ("/help", "/h"):
                    T.console.print(f"\n[cyan]{_('available_commands')}[/cyan]")
                    T.console.print(f"  [green]/help[/green]          {_('help_desc')}")
                    T.console.print(f"  [green]/rename <name>[/green]  {_('rename_desc')}")
                    T.console.print(f"  [green]/list[/green]          {_('list_desc')}")
                    T.console.print(f"  [green]/load <name>[/green]    {_('load_desc')}")
                    T.console.print(f"  [green]/delete <name>[/green]  {_('delete_desc')}")
                    T.console.print(f"  [green]/exit[/green]          {_('exit_desc')}\n")
                elif cmd == "/rename":
                    if not args:
                        T.error(_("usage_rename"))
                        continue
                    new_name = args[0].strip('"\'')
                    old_name = session.name
                    if store.rename(old_name, new_name):
                        session.name = new_name
                        store.save(session)
                        T.success(_("session_renamed", name=new_name))
                    else:
                        T.error(_("session_exists", name=new_name))
                elif cmd == "/list":
                    sessions = store.list_sessions()
                    if not sessions:
                        T.info(_("no_sessions"))
                    else:
                        T.console.print(f"\n[dim]{_('existing_sessions')}[/dim]")
                        for s in sessions:
                            T.console.print(f"  [cyan]{s['name']}[/cyan]  [dim]{s['updated_at'][:10]}  mode={s['mode']}[/dim]")
                        T.console.print()
                elif cmd == "/load":
                    if not args:
                        T.error(_("usage_load"))
                        continue
                    name = args[0].strip('"\'')
                    if not store.exists(name):
                        T.error(_("session_not_found", name=name))
                        continue
                    loaded = store.load(name)
                    if loaded:
                        session = loaded
                        T.success(_("session_loaded", name=name))
                        if session.request and session.plan_text and not session.results:
                            T.warning(_("pending_demand", request=session.request[:50]))
                    else:
                        T.error(_("session_not_found", name=name))
                elif cmd == "/delete":
                    if not args:
                        T.error(_("usage_delete"))
                        continue
                    name = args[0].strip('"\'')
                    if not store.exists(name):
                        T.error(_("session_not_found", name=name))
                        continue
                    store.delete(name)
                    T.success(_("session_deleted", name=name))
                    if session.name == name:
                        T.info(_("current_deleted"))
                        session = store.load("default") or store.create("default", session.mode, session.model)
                elif cmd in ("/exit", "/quit"):
                    T.info(_("exiting"))
                    break
                else:
                    T.error(_("unknown_command", cmd=cmd))
            else:
                hist_text = ""
                for msg in session.history[-10:]:
                    role = _("assistant") if msg['role'] == "assistant" else _("user")
                    hist_text += f"{role}: {msg['content']}\n"
                
                if hist_text:
                    prompt = f"{_('recent_history')}\n{hist_text}\n\n{_('new_message')} {user_input}"
                else:
                    prompt = user_input
                    
                classifier = make_intent_classifier(session.model)
                with T.spinner(_("agent_thinking")):
                    intent_res = await classifier.run(AgentInput(prompt=prompt))
                    intent = intent_res.response.strip().lower()
                    
                if intent == "plan":
                    T.info(_("agent_plan_triggered", req=user_input))
                    if T.confirm(_("confirm_plan_execution")):
                        if session.results or session.request:
                            session.clear_state()
                            store.save(session)
                        await run_pipeline(session, store, max_retries, request=user_input)
                    else:
                        T.info(_("plan_execution_cancelled"))
                        store.append_message(session.name, "user", user_input)
                        store.append_message(session.name, "assistant", _("plan_execution_cancelled_msg"))
                else:
                    chat_agent = make_chat_agent(session.model)
                    with T.spinner(_("agent_thinking")):
                        response = await chat_agent.run(AgentInput(prompt=prompt))
                    T.console.print(f"\n[bold green]ABCode:[/bold green] {response.response}\n")
                    store.append_message(session.name, "user", user_input)
                    store.append_message(session.name, "assistant", response.response)
                
        except KeyboardInterrupt:
            T.info(_("repl_interrupted"))
            break
        except EOFError:
            T.info(_("exiting"))
            break
        except T.UserCancelled:
            T.info(_("repl_cancelled"))
            session.clear_state()
            store.save(session)
        except T.AppExit:
            T.info(_("exiting"))
            break
        except Exception as e:
            T.error(_("unexpected_error", err=e))


# ─── Main async pipeline ──────────────────────────────────────────────────────

async def run_pipeline(
    session: SessionData,
    store: SessionStore,
    max_retries: int,
    request: str = None,
) -> None:
    model = session.model
    mode = session.mode

    # Resume from checkpoint if session has prior work
    if session.request and session.plan_text and not session.results:
        T.info(_("resuming_session", req=session.request[:80]))
        request = session.request
        plan_text = session.plan_text
        subplans = [Subplan.from_dict(d) for d in session.subplans] if session.subplans else []
        T.show_plan(plan_text, _("prev_session_plan"))
    else:
        # Fresh start
        if not request:
            return

        T.section(_("new_demand"))
        store.append_message(session.name, "user", request)
        session.request = request
        store.save(session)

        # Phase 1: panorama
        T.section(_("phase1"))
        plan_text = await generate_panorama(request, model)
        session.plan_text = plan_text
        store.save(session)

        subplans = []

    # Phase 2: refinement (only in plan/edit modes, or if no subplans yet)
    if mode in ("plan", "edit") and not subplans:
        T.section(_("phase2"))
        plan_text = await refine_plan(request, plan_text, model, session, store)
        session.plan_text = plan_text
        store.save(session)

    elif mode == "auto" and not subplans:
        T.show_plan(plan_text, _("plan_auto_mode"))

    # Phase 3: decomposition (if not already done)
    if not subplans:
        T.section(_("phase3"))
        subplans = await decompose_plan(plan_text, model)
        if not subplans:
            T.error(_("no_subplans"))
            return
        session.subplans = [sp.to_dict() for sp in subplans]
        store.save(session)

        T.subsection(_("identified_subplans", ids=[sp.id for sp in subplans]))
        for sp in subplans:
            T.info(f"  {sp.id}: {sp.objective}")

    # Phase 4: execution
    T.section(_("phase4"))
    results = await execute_subplans(
        subplans,
        request,
        model=model,
        mode=mode,
        max_retries=max_retries,
    )
    session.results = results
    store.save(session)

    # Phase 5: aggregation
    T.section(_("phase5"))
    final = await aggregate_results(results, request, model)
    store.append_message(session.name, "assistant", final)
    T.show_result(final)


# ─── CLI entrypoint ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abcode",
        description="ABCode – agente de codificação com planejamento e execução modular",
    )
    parser.add_argument("--version", action="version", version=f"ABCode {__version__}")
    parser.add_argument(
        "--mode",
        choices=["auto", "plan", "edit"],
        default=DEFAULT_MODE,
        help="Modo de execução: auto|plan|edit  (padrão: plan)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Modelo LLM a usar (padrão: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Tentativas máximas por subplano (padrão: {DEFAULT_MAX_RETRIES})",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "pt"],
        default=DEFAULT_LANG,
        help="Interface language (en|pt)",
    )
    parser.add_argument(
        "--delete",
        metavar="SESSION_NAME",
        help="Deletes the specified session and exits",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="Lists all existing sessions and exits",
    )
    return parser

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    set_lang(args.lang)
    T.print_banner(version=__version__, mode=args.mode)

    store = SessionStore(db_path=args.db)

    if args.list_sessions:
        sessions = store.list_sessions()
        if not sessions:
            T.info(_("no_sessions"))
        else:
            T.section(_("existing_sessions"))
            for s in sessions:
                T.console.print(f"  [cyan]{s['name']}[/cyan]  [dim]{s['updated_at'][:10]}  mode={s['mode']}[/dim]")
        sys.exit(0)

    if args.delete:
        if store.exists(args.delete):
            store.delete(args.delete)
            T.success(_("session_deleted", name=args.delete))
        else:
            T.error(_("session_not_found", name=args.delete))
        sys.exit(0)

    # Initialize default session
    session = store.load("default")
    if not session:
        session = store.create("default", args.mode, args.model)
    else:
        session.mode = args.mode
        session.model = args.model
        store.save(session)

    try:
        asyncio.run(repl_loop(session, store, max_retries=args.max_retries))
    except KeyboardInterrupt:
        T.warning(_("repl_interrupted"))
        sys.exit(0)


if __name__ == "__main__":
    main()
