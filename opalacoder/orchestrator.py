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

    if tasks_total > 0:
        bar_filled = min(tasks_done, tasks_total)
        bar_empty = max(0, tasks_total - bar_filled)
        bar = f"[cyan]{'█' * bar_filled}[/cyan][dim]{'░' * bar_empty}[/dim]"
        progress_line = f"[bold]Tasks:[/bold]     {tasks_done}/{tasks_total}  {bar}"
    else:
        hb = progress.heartbeat
        bar_filled = min(hb, max_hb)
        bar_empty = max(0, max_hb - bar_filled)
        bar = f"[cyan]{'█' * bar_filled}[/cyan][dim]{'░' * bar_empty}[/dim]"
        progress_line = f"[bold]Heartbeat:[/bold] {hb}/{max_hb}  {bar}"

    tool_color = {
        "write_file": "green",
        "write_content_pos": "green",
        "edit_file": "green",
        "read_file": "blue",
        "read_content_pos": "blue",
        "get_file_overview": "blue",
        "get_project_overview": "magenta",
        "find_symbol": "magenta",
        "run_command": "yellow",
        "search_code": "magenta",
        "ask_human": "red",
        "send_message": "cyan",
    }.get(progress.last_tool, "white")

    tool_line = f"[bold {tool_color}]🔧 {progress.last_tool}[/bold {tool_color}]"
    if progress.last_args:
        tool_line += f"\n   [dim]↳ {progress.last_args}[/dim]"

    content = (
        f"{progress_line}\n"
        f"[bold]Elapsed:[/bold]   {progress.elapsed()}\n\n"
        f"{tool_line}"
    )
    return Panel(
        content,
        title="[bold cyan]🤖 Orchestrator Working[/bold cyan]",
        border_style="cyan",
        expand=False,
    )


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
