"""Planning pipeline: panorama generation, user refinement loop, and decomposition."""

from agenticblocks.blocks.llm.agent import AgentInput

from .agents import make_landscape_planner, make_refinement_agent
from .structured import decompose_to_subplans, confirm_plan
from .subplan import Subplan
from .session import SessionData, SessionStore
from . import terminal as T
from .i18n import _

MAX_REFINEMENT_CYCLES = 20

# Fast-path heuristics — avoid an LLM call when user intent is unambiguous
_APPROVAL_WORDS = {
    "sim", "s", "yes", "y", "ok", "okay", "aprovado", "pode", "certo", "perfeito",
    "approved", "sure", "fine", "great", "looks good", "proceed"
}
_CHANGE_SIGNALS = {
    "quero que", "adicione", "remova", "mude", "altere", "somente", "apenas",
    "não precisa", "deve mostrar", "deve ter", "deve ser", "coloque", "tire",
    "inclua", "exclua", "troque", "substitua", "corrija", "ajuste",
    "want", "add", "remove", "change", "alter", "only", "just",
    "don't need", "must show", "must have", "must be", "put", "take",
    "include", "exclude", "replace", "substitute", "fix", "adjust", "instead"
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


async def generate_panorama(request: str, model: str) -> str:
    """Generate a high-level plan (panorama) for the given request."""
    with T.spinner(_("generating_panorama")):
        planner = make_landscape_planner(model)
        result = await planner.run(AgentInput(prompt=request))
    return result.response


async def refine_plan(
    request: str,
    plan_text: str,
    model: str,
    session: SessionData,
    store: SessionStore,
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
        T.show_plan(plan_text)

        T.info(_("cancel_reminder"))
        user_response = T.ask(_("plan_ok"))

        store.append_message(session.name, "assistant", plan_text)
        store.append_message(session.name, "user", user_response)

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
