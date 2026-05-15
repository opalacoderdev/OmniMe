"""ABCode CLI – entry point."""

import asyncio
import argparse
import sys

from . import __version__
from .config import DEFAULT_MODEL, DEFAULT_MAX_RETRIES, DEFAULT_MODE, DEFAULT_DB_PATH
from .session import SessionStore, SessionData
from .planner import generate_panorama, refine_plan, decompose_plan
from .executor import execute_subplans, aggregate_results
from .subplan import Subplan
from . import terminal as T


# ─── Session bootstrap ────────────────────────────────────────────────────────

def bootstrap_session(
    store: SessionStore,
    mode: str,
    model: str,
) -> SessionData:
    """Prompt for session name and create or resume a session."""
    T.section("Sessão")

    # Show existing sessions if any
    existing = store.list_sessions()
    if existing:
        T.console.print("[dim]Sessões existentes:[/dim]")
        for s in existing[:8]:
            T.console.print(f"  [cyan]{s['name']}[/cyan]  [dim]{s['updated_at'][:10]}  mode={s['mode']}[/dim]")
        T.console.print()

    session_name = T.ask("Nome da sessão")
    if not session_name:
        T.error("Nome de sessão não pode ser vazio.")
        sys.exit(1)

    if store.exists(session_name):
        choice = T.choose(
            f"A sessão '{session_name}' já existe. O que deseja?",
            ["Abrir sessão existente", "Criar nova (sobrescrever)"],
        )
        if choice.startswith("Abrir"):
            session = store.load(session_name)
            if session is None:
                T.error("Falha ao carregar sessão.")
                sys.exit(1)
            T.success(f"Sessão '{session_name}' carregada.")
            return session
        else:
            session = store.overwrite(session_name, mode, model)
            T.success(f"Sessão '{session_name}' recriada.")
            return session

    session = store.create(session_name, mode, model)
    T.success(f"Nova sessão '{session_name}' criada.")
    return session


# ─── Main async pipeline ──────────────────────────────────────────────────────

async def run_pipeline(
    session: SessionData,
    store: SessionStore,
    max_retries: int,
) -> None:
    model = session.model
    mode = session.mode

    # Resume from checkpoint if session has prior work
    if session.request and session.plan_text and not session.results:
        T.info(f"Retomando sessão com pedido: {session.request[:80]}")
        request = session.request
        plan_text = session.plan_text
        subplans = [Subplan.from_dict(d) for d in session.subplans] if session.subplans else []
        T.show_plan(plan_text, "Plano da Sessão Anterior")
    else:
        # Fresh start
        T.section("Nova Demanda")
        request = T.ask("Qual é a demanda de codificação?")
        if not request:
            T.error("Demanda não pode ser vazia.")
            return

        store.append_message(session.name, "user", request)
        session.request = request
        store.save(session)

        # Phase 1: panorama
        T.section("Fase 1 — Panorama")
        plan_text = await generate_panorama(request, model)
        session.plan_text = plan_text
        store.save(session)

        subplans = []

    # Phase 2: refinement (only in plan/edit modes, or if no subplans yet)
    if mode in ("plan", "edit") and not subplans:
        T.section("Fase 2 — Refinamento do Plano")
        plan_text = await refine_plan(request, plan_text, model, session, store)
        session.plan_text = plan_text
        store.save(session)

    elif mode == "auto" and not subplans:
        T.show_plan(plan_text, "Plano (modo auto)")

    # Phase 3: decomposition (if not already done)
    if not subplans:
        T.section("Fase 3 — Decomposição")
        subplans = await decompose_plan(plan_text, model)
        if not subplans:
            T.error("Nenhum subplano extraído. Encerrando.")
            return
        session.subplans = [sp.to_dict() for sp in subplans]
        store.save(session)

        T.subsection(f"Subplanos identificados: {[sp.id for sp in subplans]}")
        for sp in subplans:
            T.info(f"  {sp.id}: {sp.objective}")

    # Phase 4: execution
    T.section("Fase 4 — Execução")
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
    T.section("Fase 5 — Resultado Final")
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
        help=f"Caminho do banco de dados SQLite (padrão: {DEFAULT_DB_PATH})",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    T.print_banner(version=__version__, mode=args.mode)

    store = SessionStore(db_path=args.db)
    session = bootstrap_session(store, mode=args.mode, model=args.model)

    # Update mode/model from CLI even when resuming
    session.mode = args.mode
    session.model = args.model
    store.save(session)

    try:
        asyncio.run(run_pipeline(session, store, max_retries=args.max_retries))
    except KeyboardInterrupt:
        T.warning("Interrompido pelo usuário. Sessão salva.")
        sys.exit(0)


if __name__ == "__main__":
    main()
