"""Planning pipeline: panorama generation, user refinement loop, and decomposition."""

from agenticblocks.blocks.llm.agent import AgentInput

from .agents import make_landscape_planner, make_refinement_agent
from .structured import decompose_to_subplans, confirm_plan
from .subplan import Subplan
from .session import SessionData, SessionStore
from . import terminal as T


MAX_REFINEMENT_CYCLES = 20

# Fast-path heuristics — avoid an LLM call when user intent is unambiguous
_APPROVAL_WORDS = {"sim", "s", "yes", "y", "ok", "okay", "aprovado", "pode", "certo", "perfeito"}
_CHANGE_SIGNALS = {
    "quero que", "adicione", "remova", "mude", "altere", "somente", "apenas",
    "não precisa", "deve mostrar", "deve ter", "deve ser", "coloque", "tire",
    "inclua", "exclua", "troque", "substitua", "corrija", "ajuste",
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
    with T.spinner("Gerando panorama do plano…"):
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
        T.section("Revisão do Plano")
        T.show_plan(plan_text)

        user_response = T.ask(
            "O plano está ok? (responda 'sim' para aprovar, ou descreva as alterações desejadas)"
        )

        store.append_message(session.name, "assistant", plan_text)
        store.append_message(session.name, "user", user_response)

        # Fast heuristic — no LLM call needed for obvious cases
        fast = _fast_approval(user_response)
        if fast is True:
            T.success("Plano aprovado!")
            return plan_text
        elif fast is False:
            approved = False
        else:
            # Ambiguous — use structured LLM classification
            with T.spinner("Interpretando resposta…"):
                result = await confirm_plan(plan_text, user_response, model)
            approved = result.approved

        if approved:
            T.success("Plano aprovado!")
            return plan_text

        cycles += 1
        T.thinking("Refinando plano com base no seu feedback…")
        with T.spinner("Refinando…"):
            refined = await refinement_agent.run(
                AgentInput(
                    prompt=(
                        f"PEDIDO ORIGINAL: {request}\n"
                        f"PLANO ORIGINAL: {plan_text}\n"
                        f"FEEDBACK DO USUÁRIO: {user_response}"
                    )
                )
            )
        plan_text = refined.response

    T.warning("Número máximo de ciclos de refinamento atingido. Usando último plano.")
    return plan_text


async def decompose_plan(plan_text: str, model: str) -> list[Subplan]:
    """
    Decompose an approved plan into structured subplans using instructor.
    No regex parsing — the LLM is forced to return validated JSON directly.
    instructor retries automatically with validation error feedback on bad output.
    """
    T.thinking("Decompondo plano em subetapas…")
    with T.spinner("Decompondo…"):
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
        T.warning("Nenhum subplano retornado pelo modelo.")

    return subplans
