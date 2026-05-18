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
# ─── StructuredLLMAgentBlock subclass ──────────────────────────────────────────

from agenticblocks.blocks.llm.agent import LLMAgentBlock, AgentInput, AgentOutput
from typing import Type, Any, Optional

class StructuredAgentOutput(AgentOutput):
    structured_output: Any = Field(default=None, description="Parsed Pydantic model instance")

class StructuredLLMAgentBlock(LLMAgentBlock):
    response_schema: Optional[Type[BaseModel]] = Field(default=None, description="Pydantic model class for structured parsing")

    async def run(self, input: AgentInput) -> StructuredAgentOutput:
        if self.response_schema is None:
            parent_out = await super().run(input)
            return StructuredAgentOutput(
                response=parent_out.response,
                tool_calls_made=parent_out.tool_calls_made
            )
            
        # Use instructor with MD_JSON to ensure compat with small models
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": input.prompt}
        ]
        
        try:
            res = await _client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_model=self.response_schema,
                max_retries=3,
            )
            
            import json
            response_text = json.dumps(res.model_dump()) if hasattr(res, "model_dump") else str(res)
            return StructuredAgentOutput(
                response=response_text,
                structured_output=res
            )
        except Exception as e:
            import rich.console
            rich.console.Console().print(f"[red]StructuredLLMAgentBlock failed: {e}[/red]")
            # Fallback to empty model instantiation if possible, or parent string response
            return StructuredAgentOutput(
                response=f"Error: {e}",
                structured_output=None
            )

