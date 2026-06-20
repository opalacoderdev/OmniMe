#!/usr/bin/env python3
"""Level-3 script for the `implement-feature` skill.

Thin CLI wrapper around the existing plan→execute→verify loop
(`WorkflowOrchestratorStrategy` in omnime.workflow_orchestrator). The heavy,
deterministic logic stays in Python and is *reused* here — this script only wires
a project context and invokes `orchestrator.run(...)`.

Usage:
    python run_workflow.py --project-name <name> --request "<text>" \
        [--model <litellm-model>]

    # Or, without a saved project, point at a directory:
    python run_workflow.py --project-path /path/to/proj --request "<text>"

The script prints the orchestrator's final summary to stdout.
"""

import argparse
import asyncio
import os
import sys


def _ensure_omnime_importable() -> None:
    """Make the omnime package importable when run as a standalone script.

    The script lives at skills/implement-feature/scripts/run_workflow.py; the repo
    root (which contains the omnime package) is four levels up. We also honor
    OMNIME_ROOT if set, so the skill works when installed elsewhere.
    """
    try:
        import omnime  # noqa: F401
        return
    except Exception:
        pass
    root = os.environ.get("OMNIME_ROOT")
    if not root:
        here = os.path.abspath(__file__)
        # scripts/ -> implement-feature/ -> skills/ -> repo root
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
    if root and root not in sys.path:
        sys.path.insert(0, root)


def _resolve_model(cli_model: str | None) -> str:
    """Resolve the effective model: CLI override > project model > DEFAULT_MODEL.

    The runner forwards the SKILL.md `model:` field as --model (docs/specs/06 §1),
    so cli_model already encodes the skill's preference when present. Values
    "default"/"worker" map to the configured models.
    """
    from omnime.config import DEFAULT_MODEL, WORKER_MODEL
    if not cli_model:
        return DEFAULT_MODEL
    if cli_model == "default":
        return DEFAULT_MODEL
    if cli_model in ("worker", "alternative"):
        return WORKER_MODEL
    return cli_model


def _load_session(args):
    """Return a (session, store) pair for the orchestrator.

    Prefers a saved project (loaded by name) so memory/history are available;
    falls back to a minimal in-memory ProjectData rooted at --project-path.
    """
    from omnime.project import ProjectStore, ProjectData
    from omnime.config import DEFAULT_DB_PATH

    store = ProjectStore(db_path=args.db or DEFAULT_DB_PATH)
    if args.project_name and store.exists(args.project_name):
        session = store.load(args.project_name)
        return session, store

    # Minimal session anchored at a path (no persistence of a new project row).
    path = os.path.abspath(args.project_path or os.getcwd())
    session = ProjectData(
        name=args.project_name or "implement-feature",
        project_name=args.project_name or os.path.basename(path),
        project_path=path,
    )
    return session, store


async def _run(args) -> str:
    # Import the orchestrator registry first: omnime.orchestrator and
    # omnime.workflow_orchestrator have an order-dependent circular import
    # (the registry module imports the strategy at the bottom as a registration
    # side-effect). Importing the registry first resolves the cycle — the same
    # order cli.py uses.
    import omnime.orchestrator  # noqa: F401
    from workflow_orchestrator import WorkflowOrchestratorStrategy

    model = _resolve_model(args.model)
    session, store = _load_session(args)

    strategy = WorkflowOrchestratorStrategy(model=model)
    return await strategy.run(
        user_request=args.request,
        history="",
        session=session,
        store=store,
        project_skills=[],
        interactive=args.interactive,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_workflow.py",
        description="implement-feature skill engine (plan→execute→verify).",
    )
    parser.add_argument("--request", default=None, help="User request to implement.")
    parser.add_argument("--request-file", default=None,
                        help="Path to a file containing the request (avoids shell "
                             "quoting of complex requests). Takes precedence over --request.")
    parser.add_argument("--model", default=None,
                        help="Model override (default/worker or a litellm id).")
    parser.add_argument("--project-name", default=None,
                        help="Name of a saved project to load (memory + history).")
    parser.add_argument("--project-path", default=None,
                        help="Project directory when no saved project is used.")
    parser.add_argument("--db", default=None, help="Sessions DB path.")
    parser.add_argument("--interactive", action="store_true",
                        help="Enable interactive plan refinement (needs a terminal). "
                             "Default: non-interactive (auto-approve the plan).")
    args = parser.parse_args(argv)

    # Resolve the request from --request-file (preferred) or --request.
    if args.request_file:
        with open(args.request_file, "r", encoding="utf-8") as f:
            args.request = f.read().strip()
    if not args.request:
        parser.error("one of --request or --request-file is required")

    _ensure_omnime_importable()
    result = asyncio.run(_run(args))
    print(result if result else "(no output)")
    return 0


if __name__ == "__main__":
    _ensure_omnime_importable()
    raise SystemExit(main())
