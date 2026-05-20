"""
Test script: runs the full OpalaCoder pipeline on the micalc project,
bypassing interactive input (auto-approves the plan), and logs everything
to /home/gilzamir/log.log.

Run with:
    cd /home/gilzamir/projetos/OpalaCoder
    python run_micalc_test.py 2>&1 | tee -a /home/gilzamir/log.log
"""

import asyncio
import sys
import time
from unittest.mock import patch

LOG_PATH = "/home/gilzamir/log.log"

def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)

# ── Redirect stderr so DEBUG prints go to the same stream ─────────────────────
sys.stderr = sys.stdout

REQUEST = (
    "resolva o erro javascript persistente: "
    "Uncaught SyntaxError: redeclaration of const display script.js:248:7"
    "note: Previously declared at line 12, column 7. "
    "Faça em apenas um ou dois passos, não mais do que isso. "
    "E foque em corrigir o erro."
)

async def main():
    log("=" * 70)
    log("OpalaCoder micalc integration test")
    log(f"Request: {REQUEST}")
    log("=" * 70)

    # ── Load session ──────────────────────────────────────────────────────────
    from opalacoder.project import ProjectStore, ProjectData
    from opalacoder.session import SessionStore

    session_store = SessionStore()
    projects = session_store.list_projects()
    micalc_data = next((p for p in projects if p["name"] == "micalc"), None)
    if not micalc_data:
        log("ERROR: micalc project not found in session store")
        return

    log(f"Project found: {micalc_data}")

    store = ProjectStore()
    project = store.load("micalc")
    if project is None:
        from opalacoder.config import DEFAULT_MODEL
        log("Creating fresh micalc ProjectData from session record")
        project = ProjectData(
            name="micalc",
            project_name="micalc",
            project_path=micalc_data["project_path"],
            model=DEFAULT_MODEL,
        )

    log(f"Project path: {project.project_path}")
    log(f"Model: {project.model}")

    # ── Patch interactive inputs to auto-approve ──────────────────────────────
    # T.ask → empty string = auto-approve in refine_plan
    # T.show_plan, T.section, T.success, T.info, T.thinking, T.warning → log only

    import opalacoder.terminal as T_mod
    import opalacoder.planner as planner_mod

    original_show_plan = T_mod.show_plan if hasattr(T_mod, "show_plan") else None

    def fake_ask(prompt="", **kwargs):
        log(f"[T.ask] prompt={prompt!r} → auto-approving (empty Enter)")
        return ""

    def fake_show_plan(text, **kwargs):
        log(f"[T.show_plan] Plan text ({len(text)} chars):\n{text}\n")

    def fake_section(title, **kwargs):
        log(f"\n{'─'*60}\n[SECTION] {title}\n{'─'*60}")

    def fake_success(msg, **kwargs):
        log(f"[SUCCESS] {msg}")

    def fake_info(msg, **kwargs):
        log(f"[INFO] {msg}")

    def fake_warning(msg, **kwargs):
        log(f"[WARNING] {msg}")

    def fake_thinking(msg, **kwargs):
        log(f"[THINKING] {msg}")

    patches = [
        patch.object(T_mod, "ask", side_effect=fake_ask),
        patch.object(T_mod, "show_plan", side_effect=fake_show_plan),
        patch.object(T_mod, "section", side_effect=fake_section),
        patch.object(T_mod, "success", side_effect=fake_success),
        patch.object(T_mod, "info", side_effect=fake_info),
        patch.object(T_mod, "warning", side_effect=fake_warning),
    ]
    if hasattr(T_mod, "thinking"):
        patches.append(patch.object(T_mod, "thinking", side_effect=fake_thinking))

    # Also patch Path.write_text for plan.md to just log it
    import pathlib
    _orig_write_text = pathlib.Path.write_text

    def fake_write_text(self, data, *args, **kwargs):
        if "plan.md" in str(self) or "PLAN" in str(self).upper():
            log(f"[PLAN FILE] Writing plan.md ({len(data)} chars):\n{data}\n")
        return _orig_write_text(self, data, *args, **kwargs)

    patches.append(patch.object(pathlib.Path, "write_text", fake_write_text))

    # ── Run pipeline ──────────────────────────────────────────────────────────
    log("\nStarting run_pipeline...\n")
    start = time.monotonic()

    from opalacoder.cli import run_pipeline

    with __import__("contextlib").ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        result = await run_pipeline(
            project=project,
            store=store,
            max_retries=3,
            request=REQUEST,
        )

    elapsed = time.monotonic() - start
    log(f"\n{'='*70}")
    log(f"Pipeline finished in {elapsed:.1f}s")
    log(f"Final result:\n{result}")
    log("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
