"""Structured LLM output using instructor + Pydantic.

All LLM calls that must return structured data go through here.
instructor automatically retries with validation error feedback when the
model produces malformed JSON, making this robust for small models.
"""

import instructor
import litellm
from pydantic import BaseModel, Field

# MD_JSON works with any model: asks for JSON inside a markdown block,
# no native tool-calling support required (safe for local/small models).
_client = instructor.from_litellm(litellm.acompletion, mode=instructor.Mode.MD_JSON)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SubplanSchema(BaseModel):
    id: str = Field(description="Identificador único no formato SP-<n>, ex: SP-1")
    phase: str = Field(description="Nome curto da fase do plano")
    objective: str = Field(description="O que este subplano entrega")
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Lista de IDs de subplanos que devem ser concluídos antes deste (ex: ['SP-1']). Vazio se não houver.",
    )
    steps: list[str] = Field(
        description="Ações concretas e atômicas, máximo 5 itens"
    )
    completion_criterion: str = Field(
        description="Como validar que este subplano foi concluído com sucesso"
    )


class DecompositionResult(BaseModel):
    subplans: list[SubplanSchema] = Field(
        description="Lista ordenada de subplanos executáveis derivados do panorama"
    )


class ConfirmationResult(BaseModel):
    approved: bool = Field(
        description="True se o usuário aprovou o plano, False se quer alterações"
    )


# ─── Callers ──────────────────────────────────────────────────────────────────

_DECOMPOSE_SYSTEM = """Você é um agente de decomposição de planos de software.
Receberá um PANORAMA GERAL e deve decompor cada fase em subplanos executáveis e independentes.

Regras obrigatórias:
- Cada subplano deve ser executável por um agente separado
- Passos devem ser ações concretas e atômicas (máximo 5 por subplano)
- Respeite dependências reais entre subplanos via o campo prerequisites
- IDs devem ser sequenciais: SP-1, SP-2, SP-3, ...
"""

_CONFIRM_SYSTEM = """Você determina se um usuário APROVOU um plano ou quer MODIFICÁ-LO.

Retorne approved=true APENAS para aprovação clara e sem condições.
Exemplos de aprovação: "sim", "ok", "pode prosseguir", "perfeito", "tudo certo".

Retorne approved=false se o usuário pediu qualquer alteração, adição ou remoção,
mesmo que parcial ou educada.
Exemplos de não-aprovação: "quero que...", "adicione...", "mude...", "somente...",
"não precisa de...", "o app deve...".
"""


async def decompose_to_subplans(
    plan_text: str,
    model: str,
    max_retries: int = 3,
    timeout: int = 120,
) -> DecompositionResult:
    """
    Ask the LLM to decompose a plan into structured subplans.
    Uses MD_JSON mode — works with any model, including local/small ones.
    instructor retries automatically with validation feedback on bad output.
    """
    return await _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _DECOMPOSE_SYSTEM},
            {"role": "user", "content": f"PANORAMA:\n{plan_text}"},
        ],
        response_model=DecompositionResult,
        max_retries=max_retries,
        timeout=timeout,
    )


async def confirm_plan(
    plan_text: str,
    user_response: str,
    model: str,
    max_retries: int = 3,
    timeout: int = 60,
) -> ConfirmationResult:
    """
    Ask the LLM to classify whether the user approved the plan.
    Uses MD_JSON mode — works with any model, including local/small ones.
    """
    return await _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _CONFIRM_SYSTEM},
            {
                "role": "user",
                "content": f"PLANO:\n{plan_text}\n\nRESPOSTA DO USUÁRIO:\n{user_response}",
            },
        ],
        response_model=ConfirmationResult,
        max_retries=max_retries,
        timeout=timeout,
    )
