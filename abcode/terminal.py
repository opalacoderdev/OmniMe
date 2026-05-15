"""Elegant terminal output utilities for ABCode using Rich."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.rule import Rule
from rich import print as rprint
from contextlib import contextmanager
import sys

console = Console(highlight=False)


# ─── Branding ─────────────────────────────────────────────────────────────────

BANNER = r"""
    _    ____  ____          _
   / \  | __ )/ ___|___   __| | ___
  / _ \ |  _ \ |   / _ \ / _` |/ _ \
 / ___ \| |_) | |__| (_) | (_| |  __/
/_/   \_\____/ \____\___/ \__,_|\___|
"""


def print_banner(version: str = "0.1.0", mode: str = "plan") -> None:
    text = Text(BANNER, style="bold cyan")
    console.print(text)
    console.print(
        f"  [dim]version {version}[/dim]  "
        f"[bold]mode:[/bold] [yellow]{mode}[/yellow]"
    )
    console.print()


# ─── Section headers ──────────────────────────────────────────────────────────

def section(title: str, style: str = "bold blue") -> None:
    console.print(Rule(f"[{style}]{title}[/{style}]", style="dim"))


def subsection(title: str) -> None:
    console.print(f"\n[bold cyan]▶ {title}[/bold cyan]")


# ─── Info / status ────────────────────────────────────────────────────────────

def info(msg: str) -> None:
    console.print(f"[dim]  {msg}[/dim]")


def success(msg: str) -> None:
    console.print(f"[bold green]  ✓ {msg}[/bold green]")


def warning(msg: str) -> None:
    console.print(f"[bold yellow]  ⚠ {msg}[/bold yellow]")


def error(msg: str) -> None:
    console.print(f"[bold red]  ✗ {msg}[/bold red]")


def thinking(msg: str) -> None:
    console.print(f"[italic dim cyan]  💭 {msg}[/italic dim cyan]")


# ─── Panels ───────────────────────────────────────────────────────────────────

def show_plan(plan_text: str, title: str = "Plano Gerado") -> None:
    console.print(
        Panel(plan_text, title=f"[bold]{title}[/bold]", border_style="cyan", expand=False)
    )


def show_result(text: str, title: str = "Resultado Final") -> None:
    console.print(
        Panel(text, title=f"[bold green]{title}[/bold green]", border_style="green")
    )


def show_error_report(errors: list[tuple[str, str]]) -> None:
    table = Table(title="Erros de Execução", border_style="red", show_lines=True)
    table.add_column("Subplano", style="bold yellow")
    table.add_column("Erro", style="red")
    for sp_id, err in errors:
        table.add_row(sp_id, err[:300])
    console.print(table)


# ─── Spinner context ──────────────────────────────────────────────────────────

@contextmanager
def spinner(label: str):
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]{label}[/cyan]"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        yield progress


# ─── User prompts ─────────────────────────────────────────────────────────────

def ask(prompt: str) -> str:
    console.print(f"\n[bold yellow]?[/bold yellow] {prompt}")
    return input("  → ").strip()


def confirm(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    console.print(f"\n[bold yellow]?[/bold yellow] {prompt} {hint}")
    raw = input("  → ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "sim", "s")


def choose(prompt: str, options: list[str]) -> str:
    """Let user pick from a numbered list; returns chosen option string."""
    console.print(f"\n[bold yellow]?[/bold yellow] {prompt}")
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan]) {opt}")
    while True:
        raw = input("  → ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        # accept text match too
        matches = [o for o in options if o.lower().startswith(raw.lower())]
        if len(matches) == 1:
            return matches[0]
        console.print("  [red]Opção inválida, tente novamente.[/red]")


# ─── Subplan progress table ───────────────────────────────────────────────────

def subplan_status_table(statuses: list[tuple[str, str, str]]) -> None:
    """statuses: [(sp_id, objective, status_label), ...]"""
    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Objetivo")
    table.add_column("Status", width=12)
    for sp_id, obj, status in statuses:
        color = {"OK": "green", "FALHOU": "red", "ERRO": "red", "→": "yellow"}.get(
            status.upper().split()[0], "white"
        )
        table.add_row(sp_id, obj[:70], f"[{color}]{status}[/{color}]")
    console.print(table)
