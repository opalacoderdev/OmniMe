"""Print exactly what the planner oracle receives and returns for a real request.

Loads the project from the OpalaCoder store (same path as the CLI), so the
project_path, snapshot, and skill tools are identical to a real run.

Usage:
    python tests/test_planner_output.py "micalc" "O botão 9 da calculadora funciona como clear"
    python -m pytest tests/test_planner_output.py -s -v -k test_planner_for_micalc_bug
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from opalacoder.project import ProjectStore
from opalacoder.tools import set_project_context, get_project_path
from opalacoder.code_index import CODE_INDEX
from opalacoder.skills import active_skills
from opalacoder.orchestrator import get_orchestrator
from opalacoder.workflow_orchestrator import PlanOutput, _project_snapshot, _oracle
from opalacoder.config import get_agent_llm_kwargs, get_agent_model, DEFAULT_MODEL

DIVIDER = "=" * 80
SEP = "-" * 80


def _extract_file_snippets(request_text: str, max_bytes: int = 3000) -> str:
    import re
    from pathlib import Path
    root = Path(get_project_path())
    mentioned = re.findall(r'\b[\w/-]+\.(?:js|ts|py|css|html|json|jsx|tsx|md)\b', request_text)
    parts = []
    seen: set[str] = set()
    for fname in mentioned:
        if fname in seen:
            continue
        seen.add(fname)
        matches = list(root.rglob(fname))
        if not matches:
            continue
        p = matches[0]
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            snippet = content[:max_bytes]
            if len(content) > max_bytes:
                snippet += f"\n...(truncated, {len(content)} bytes)"
            rel = str(p.relative_to(root))
            numbered = "\n".join(f"{i+1:4d}  {l}" for i, l in enumerate(snippet.splitlines()))
            parts.append(f"### {rel}\n```\n{numbered}\n```")
        except Exception:
            pass
    return "\n\n".join(parts)


async def run_planner_test(project_name: str, user_request: str):
    # ── 1. Load project from store (same as CLI) ──────────────────────────
    # Use the same db path the CLI uses (falls back to OpalaCoder's projects.db)
    db_path = os.path.expanduser("~/.opalacoder/sessions.db")
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects.db")
    store = ProjectStore(db_path=db_path)
    project = store.load(project_name)
    if project is None:
        print(f"\nERROR: project '{project_name}' not found in store at {db_path}")
        print("Available projects:")
        for p in store.list_projects():
            print(f"  {p['name']}  [{p.get('project_path', '?')}]")
        return None

    # ── 2. Set project context (same as repl_loop) ────────────────────────
    set_project_context(project, store)
    project_skills = active_skills(project.project_path)

    print(f"\n{DIVIDER}")
    print(f"Project:  {project.name}  →  {project.project_path}")
    print(f"Skills:   {project.skills}")
    print(f"Resolved project_path: {get_project_path()}")

    # ── 3. Build code index (same as orchestrator.run) ────────────────────
    CODE_INDEX.set_project(get_project_path())
    stats = CODE_INDEX.build()
    print(f"Code index: {stats}")

    # Plugin-tools were retired: skills run detectors via explicit Level-3 scripts.
    skill_tool_names: list[str] = []

    # ── 5. Build planning prompt (same as _orchestration_loop) ────────────
    model = get_agent_model("orchestrator", DEFAULT_MODEL)
    llm_kwargs = get_agent_llm_kwargs("orchestrator")

    project_context = project.context_header() if hasattr(project, "context_header") else f"[PATH: {get_project_path()}]"
    strategy = get_orchestrator("workflow", model)
    planner_sys = strategy._planner_system(
        project_context,
        session=project,
        skill_tool_names=skill_tool_names or None,
    )

    snapshot = _project_snapshot()
    file_snippets = _extract_file_snippets(user_request)

    # Replicate skill tool pre-scan (same logic as _orchestration_loop)
    skill_tool_output = ""
    for st in skill_tools:
        try:
            raw_fn = getattr(st, "_func", None)
            if raw_fn is None and callable(st):
                raw_fn = st
            if raw_fn is None:
                continue
            result_raw = raw_fn(".")
            if result_raw and isinstance(result_raw, str):
                blocking_lines = [
                    line for line in result_raw.splitlines()
                    if any(tag in line for tag in ("[CONTRACT ERROR]", "[SYNTAX ERROR]", "[ERROR]"))
                ]
                if blocking_lines:
                    tool_name = getattr(st, "name", getattr(raw_fn, "__name__", "tool"))
                    skill_tool_output += f"[{tool_name}]\n" + "\n".join(blocking_lines) + "\n"
        except Exception as e:
            skill_tool_output += f"[tool error: {e}]\n"

    file_section = ""
    if file_snippets or skill_tool_output:
        file_section = "\nRelevant file contents and diagnostics (read before planning):\n"
        if file_snippets:
            file_section += file_snippets + "\n"
        if skill_tool_output:
            file_section += "\nSkill tool pre-scan (run before planning — tells you WHICH FILE has the bug):\n" + skill_tool_output

    planning_prompt = (
        f"Project files:\n{snapshot}\n"
        f"{file_section}\n"
        f"Conversation history:\n\n"
        f"User request:\n{user_request}"
    )

    # ── 6. Print everything ───────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("PLANNER SYSTEM PROMPT:")
    print(SEP)
    print(planner_sys)

    print(f"\n{DIVIDER}")
    print("PLANNING PROMPT (user message):")
    print(SEP)
    print(planning_prompt)

    # ── 7. Call oracle ────────────────────────────────────────────────────
    plan = await _oracle(
        PlanOutput, planner_sys, planning_prompt,
        model=model, llm_kwargs=llm_kwargs,
    )

    print(f"\n{DIVIDER}")
    print("PLANNER OUTPUT (parsed):")
    print(SEP)
    if plan is None:
        print("(oracle returned None — failed to produce valid JSON after retries)")
    else:
        print(json.dumps(
            {"tasks": [t.model_dump() for t in plan.tasks]},
            indent=2, ensure_ascii=False,
        ))
    print(DIVIDER)
    return plan


def test_planner_for_micalc_bug(capsys):
    """Inspect what the planner generates for the known micalc bug report."""
    plan = asyncio.run(run_planner_test("micalc", "O botão 9 da calculadora funciona como clear"))
    with capsys.disabled():
        pass
    assert plan is not None, "Planner returned None"


if __name__ == "__main__":
    project_name = sys.argv[1] if len(sys.argv) > 1 else "micalc"
    request = sys.argv[2] if len(sys.argv) > 2 else "O botão 9 da calculadora funciona como clear"
    asyncio.run(run_planner_test(project_name, request))
