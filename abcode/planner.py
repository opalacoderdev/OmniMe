"""Planning pipeline: panorama generation, user refinement loop, and decomposition."""

import os
import re
from pathlib import Path

from agenticblocks.blocks.llm.agent import AgentInput

from .agents import make_landscape_planner, make_refinement_agent
from .structured import decompose_to_subplans, confirm_plan
from .subplan import Subplan
from .project import ProjectData, ProjectStore
from . import terminal as T
from .i18n import _

PLAN_FILE = "plan.md"

MAX_REFINEMENT_CYCLES = 20

# Fast-path heuristics — avoid an LLM call when user intent is unambiguous
_APPROVAL_WORDS = {
    # Portuguese
    "sim", "s", "ok", "okay", "aprovado", "pode", "certo", "perfeito",
    "tudo certo", "tudo bem", "pode ir", "vai", "prossiga", "continua",
    "continue", "confirmo", "confirmado", "aceito", "aceitar", "beleza",
    "ótimo", "excelente", "correto", "está bom", "está ótimo", "positivo",
    # English
    "yes", "y", "approved", "sure", "fine", "great", "looks good", "proceed",
    "go ahead", "confirmed", "confirm", "good", "perfect", "done", "alright",
    "all good", "that's good", "sounds good", "let's go", "execute", "run it",
}
_CHANGE_SIGNALS = {
    # Portuguese
    "quero que", "adicione", "remova", "mude", "altere", "somente", "apenas",
    "não precisa", "deve mostrar", "deve ter", "deve ser", "coloque", "tire",
    "inclua", "exclua", "troque", "substitua", "corrija", "ajuste", "falta",
    "precisa de", "faltou", "acrescente", "retire", "prefiro", "melhor seria",
    # English
    "want", "add", "remove", "change", "alter", "only", "just",
    "don't need", "must show", "must have", "must be", "put", "take",
    "include", "exclude", "replace", "substitute", "fix", "adjust", "instead",
    "also", "but", "however", "missing", "need", "should", "could you",
    "can you", "please add", "please remove", "please change",
}


def _fast_approval(user_response: str) -> bool | None:
    """
    Returns True (approved), False (wants changes), or None (ask the LLM).
    Avoids an LLM round-trip when the intent is obvious.
    """
    normalized = user_response.strip().lower().rstrip(".,!?")
    if normalized in _APPROVAL_WORDS:
        return True
    if any(signal in normalized for signal in _CHANGE_SIGNALS):
        return False
    return None


_TOOL_CALL_PATTERN = re.compile(
    r"(`{1,3}[^`]*`{1,3}|\b(?:ask_human|input|print|get_preferences)\s*\([^)]*\))",
    re.DOTALL,
)
_PREAMBLE_PATTERN = re.compile(
    r"^.*?(?:before (?:creating|planning)|need to (?:run|conduct|perform)|requirements elicitation)[^\n]*\n+",
    re.IGNORECASE | re.DOTALL,
)


def _sanitize_panorama(text: str) -> str:
    """Strip tool calls and elicitation preambles from raw LLM panorama output."""
    text = _PREAMBLE_PATTERN.sub("", text)
    text = _TOOL_CALL_PATTERN.sub("", text)
    # Collapse leftover blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def generate_panorama(request: str, model: str, history: str = "") -> str:
    """Generate a high-level plan (panorama) for the given request."""
    prompt = request
    if history:
        prompt = f"[CONVERSATION HISTORY]\n{history}\n[END HISTORY]\n\n[USER TASK]:\n{request}"

    with T.spinner(_("generating_panorama")):
        planner = make_landscape_planner(model)
        result = await planner.run(AgentInput(prompt=prompt))
    return _sanitize_panorama(result.response)


async def refine_plan(
    request: str,
    plan_text: str,
    model: str,
    session: ProjectData,
    store: ProjectStore,
) -> str:
    """
    Interactive refinement loop: show plan → ask user → refine or approve.
    Confirmation uses instructor structured output — immune to formatting variations.
    Returns the final approved plan text.
    """
    refinement_agent = make_refinement_agent(model)
    cycles = 0

    while cycles < MAX_REFINEMENT_CYCLES:
        T.section(_("plan_review"))

        # Show plan in terminal and write to file so user can also edit it externally
        T.show_plan(plan_text)
        plan_path = Path(PLAN_FILE).resolve()
        try:
            plan_path.write_text(plan_text, encoding="utf-8")
            T.success(_("plan_saved_to_file", path=str(plan_path)))
        except OSError as e:
            T.warning(f"Could not write {PLAN_FILE}: {e}")

        T.info(_("cancel_reminder"))
        user_response = T.ask(_("plan_confirm_after_edit"))

        # Read back the (possibly edited) file before using plan_text further
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
        except OSError as e:
            T.warning(_("plan_file_read_error", err=e))

        store.append_message(session, "assistant", plan_text)
        store.append_message(session, "user", user_response)

        # Empty Enter or explicit approval words → approved as-is
        if not user_response:
            T.success(_("plan_approved"))
            return plan_text

        # Fast heuristic — no LLM call needed for obvious cases
        fast = _fast_approval(user_response)
        if fast is True:
            T.success(_("plan_approved"))
            return plan_text
        elif fast is False:
            approved = False
        else:
            # Ambiguous — use structured LLM classification
            with T.spinner(_("interpreting_response")):
                result = await confirm_plan(plan_text, user_response, model)
            approved = result.approved

        if approved:
            T.success(_("plan_approved"))
            return plan_text

        cycles += 1
        T.thinking(_("refining_plan"))
        with T.spinner(_("refining")):
            refined = await refinement_agent.run(
                AgentInput(
                    prompt=_("refinement_prompt", request=request, plan_text=plan_text, feedback=user_response)
                )
            )
        plan_text = refined.response

    T.warning(_("max_refinement_cycles"))
    return plan_text


async def decompose_plan(plan_text: str, model: str) -> list[Subplan]:
    """
    Decompose an approved plan into structured subplans using instructor.
    No regex parsing — the LLM is forced to return validated JSON directly.
    instructor retries automatically with validation error feedback on bad output.
    """
    T.thinking(_("decomposing_plan"))
    with T.spinner(_("decomposing")):
        result = await decompose_to_subplans(plan_text, model)

    subplans = [
        Subplan(
            id=sp.id,
            phase=sp.phase,
            objective=sp.objective,
            prerequisites=sp.prerequisites,
            steps=sp.steps,
            completion_criterion=sp.completion_criterion,
        )
        for sp in result.subplans
    ]

    if not subplans:
        T.warning(_("no_subplan_returned"))

    return subplans
