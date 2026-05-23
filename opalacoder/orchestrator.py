"""Orchestrator registry, base class, and shared UI helpers.

Each concrete strategy lives in its own module:
  - workflow_orchestrator.py    → WorkflowOrchestratorStrategy     ("workflow")

Importing this module triggers registration of all bundled strategies via the
side-effect imports at the bottom of the file.
"""

import abc
import logging
import os

from rich.panel import Panel

# ─── Suppress non-fatal LiteLLM serialization noise ──────────────────────────

class _SuppressMockToolCallErrors(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "__pydantic_fields_set__" not in record.getMessage()


logging.getLogger("LiteLLM").addFilter(_SuppressMockToolCallErrors())

# ─── Shared constant ──────────────────────────────────────────────────────────

CHECKPOINT_SUBPATH = os.path.join(".opalacoder", "session_state.json")

# ─── Registry ─────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, type["BaseOrchestratorStrategy"]] = {}


def register_orchestrator(name: str):
    """Class decorator that registers an orchestrator strategy under *name*."""
    def decorator(cls: type) -> type:
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_orchestrator(strategy: str, model: str) -> "BaseOrchestratorStrategy":
    """Instantiate the orchestrator registered under *strategy*.

    Raises ValueError for unknown names so a misconfigured agents.yaml fails loudly.
    """
    cls = _REGISTRY.get(strategy)
    if cls is None:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(
            f"Unknown orchestrator strategy '{strategy}'. Available: {available}"
        )
    return cls(model=model)


# ─── Abstract base ────────────────────────────────────────────────────────────

class BaseOrchestratorStrategy(abc.ABC):
    def __init__(self, model: str):
        self.model = model

    @abc.abstractmethod
    async def run(self, user_request: str, history: str, **kwargs) -> str:
        """Execute the orchestration logic for the given user request."""


# ─── Shared UI helper ─────────────────────────────────────────────────────────

def _build_progress_panel(progress: object, max_hb: int) -> Panel:
    """Build a Rich Panel showing current agent activity."""
    tasks_done = getattr(progress, "tasks_done", 0)
    tasks_total = getattr(progress, "tasks_total", 0)

    # ── Progress bar ────────────────────────────────────────────────────
    BAR_WIDTH = 20
    if tasks_total > 0:
        filled = min(tasks_done, tasks_total)
        empty = max(0, tasks_total - filled)
        bar = f"[cyan]{'█' * filled}[/cyan][dim]{'░' * empty}[/dim]"
        progress_line = f"[bold]Tasks:[/bold]  {tasks_done}/{tasks_total}  {bar}"
    else:
        hb = getattr(progress, "heartbeat", 0)
        filled = min(hb, BAR_WIDTH)
        empty = max(0, BAR_WIDTH - filled)
        bar = f"[cyan]{'█' * filled}[/cyan][dim]{'░' * empty}[/dim]"
        progress_line = f"[bold]Step:[/bold]   {hb}/{max_hb}  {bar}"

    # ── Active tool ─────────────────────────────────────────────────────
    tool_color = {
        "write_file": "green", "write_content_pos": "green", "edit_file": "green",
        "read_file": "blue", "read_content_pos": "blue", "get_file_overview": "blue",
        "get_project_overview": "magenta", "find_symbol": "magenta",
        "run_command": "yellow", "search_code": "magenta",
        "ask_human": "bright_red", "send_message": "cyan",
        "search_bugs": "magenta",
    }.get(progress.last_tool, "white")
    tool_line = f"[bold {tool_color}]⚙  {progress.last_tool}[/bold {tool_color}]"
    if progress.last_args:
        tool_line += f"\n   [dim]↳ {progress.last_args}[/dim]"

    # ── Error counters ──────────────────────────────────────────────────
    task_failures = getattr(progress, "task_failures", 0)
    worker_errors = getattr(progress, "worker_errors", 0)
    lint_errors   = getattr(progress, "lint_errors", 0)
    plan_retries  = getattr(progress, "plan_retries", 0)

    def _counter(label: str, value: int, warn_at: int = 1) -> str:
        if value == 0:
            return f"[dim]{label}: 0[/dim]"
        color = "red" if value >= warn_at * 2 else "yellow"
        return f"[{color}]{label}: {value}[/{color}]"

    counters = (
        f"{_counter('review fails', task_failures)}  "
        f"{_counter('worker err', worker_errors)}  "
        f"{_counter('lint err', lint_errors)}  "
        f"{_counter('plan retry', plan_retries)}"
    )

    # ── Recent events log ────────────────────────────────────────────────
    recent_events: list[str] = getattr(progress, "recent_events", [])
    events_section = ""
    if recent_events:
        event_lines = "\n".join(f"  {e}" for e in recent_events[-5:])
        events_section = f"\n[dim]─── Recent events ───[/dim]\n{event_lines}"

    # ── Title: turns red when errors accumulate ──────────────────────────
    total_errors = task_failures + worker_errors + lint_errors
    if total_errors >= 3:
        title = "[bold red]🔴 Orchestrator — Errors Detected[/bold red]"
        border = "red"
    elif total_errors >= 1:
        title = "[bold yellow]🟡 Orchestrator Working[/bold yellow]"
        border = "yellow"
    else:
        title = "[bold cyan]🤖 Orchestrator Working[/bold cyan]"
        border = "cyan"

    content = (
        f"{progress_line}\n"
        f"[bold]Elapsed:[/bold] {progress.elapsed()}\n\n"
        f"{tool_line}\n\n"
        f"{counters}"
        f"{events_section}"
    )
    return Panel(content, title=title, border_style=border, expand=False)


# ─── Shared response helper ───────────────────────────────────────────────────

def _deduplicate_response(text: str) -> str:
    """Remove consecutive duplicate paragraphs from the agent response."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    seen: list[str] = []
    for p in paragraphs:
        if not seen or p != seen[-1]:
            seen.append(p)
    return "\n".join(seen)


# ─── Register bundled strategies (side-effect imports) ───────────────────────
# Each module decorates its class with @register_orchestrator, so importing it
# is enough to populate _REGISTRY.

from .workflow_orchestrator import WorkflowOrchestratorStrategy      # noqa: F401
