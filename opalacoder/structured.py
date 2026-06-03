"""Structured LLM output via LLMAgentBlock + response_schema.

All LLM calls that must return structured data go through here.
LLMAgentBlock handles JSON parsing, markdown-fence stripping, and retry
with validation feedback — no external instructor dependency needed.
"""

from pydantic import BaseModel, Field
from agenticblocks.blocks.llm.agent import LLMAgentBlock, AgentInput


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ConfirmationResult(BaseModel):
    approved: bool = Field(
        description="True se o usuário aprovou o plano, False se quer alterações"
    )


# ─── Callers ──────────────────────────────────────────────────────────────────

_CONFIRM_SYSTEM = """Determine if the user APPROVED the plan or wants changes.
Return approved=true only for clear unconditional approval (e.g. "yes", "ok", "proceed").
Return approved=false for any change request, however polite (e.g. "add", "remove", "change").
Output valid JSON only. DO NOT output any explanation or trailing text."""


async def confirm_plan(
    plan_text: str,
    user_response: str,
    model: str,
    timeout: int = 60,
) -> ConfirmationResult:
    """
    Ask the LLM to classify whether the user approved the plan.
    Uses LLMAgentBlock with response_schema — works with any model.
    """
    agent = LLMAgentBlock(
        name="confirm_plan",
        system_prompt=_CONFIRM_SYSTEM,
        model=model,
        response_schema=ConfirmationResult,
        max_iterations=1,
        model_kwargs={"timeout": timeout},
    )
    prompt = f"PLANO:\n{plan_text}\n\nRESPOSTA DO USUÁRIO:\n{user_response}"
    result = await agent.run(AgentInput(prompt=prompt))
    if result.structured_output is not None:
        return result.structured_output
    # Fallback: try to parse from text response
    import json, re
    text = (result.response or "").strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return ConfirmationResult.model_validate_json(m.group())
    return ConfirmationResult(approved=False)
