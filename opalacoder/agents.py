"""Agent factory functions for OpalaCoder."""

from agenticblocks.blocks.llm.agent import LLMAgentBlock

from .config import DEFAULT_MODEL, get_agent_llm_kwargs, get_agent_model, get_project_agent_params
from . import i18n

def _make_llm(name: str, system_prompt: str, model: str | None, disable_lang_rule: bool = False, **kwargs) -> LLMAgentBlock:
    lang_name = "English" if i18n._LANG == "en" else "Portuguese"
    lang_rule = ""
    if not disable_lang_rule:
        lang_rule = f"\n\nCRITICAL RULE: The user interface language is set to {lang_name}. You MUST translate your final responses, explanations, and output to {lang_name}. However, keep your internal reasoning, code variables, and logic in English."

    resolved_model = get_agent_model(name, model or DEFAULT_MODEL)

    # Start from per-agent config, then apply any explicit caller overrides (caller wins)
    merged_kwargs = {**get_agent_llm_kwargs(name), **kwargs.get("model_kwargs", {})}
    
    if merged_kwargs.get("api_base"):
        if resolved_model.startswith("ollama/") or resolved_model.startswith("ollama_chat/"):
            if merged_kwargs["api_base"].endswith("/v1"):
                merged_kwargs["api_base"] = merged_kwargs["api_base"][:-3]
            elif merged_kwargs["api_base"].endswith("/v1/"):
                merged_kwargs["api_base"] = merged_kwargs["api_base"][:-4]
                
    kwargs["model_kwargs"] = merged_kwargs

    # Apply project-level agent constructor overrides (e.g. max_iterations, debug)
    agent_params = get_project_agent_params()
    for key in ("max_iterations", "max_tool_calls", "on_max_iterations", "debug", "use_shared_router"):
        if key in agent_params and key not in kwargs:
            kwargs[key] = agent_params[key]

    return LLMAgentBlock(
        name=name,
        description=name,
        model=resolved_model,
        system_prompt=system_prompt + lang_rule,
        **kwargs,
    )


def make_landscape_planner(model: str | None = None) -> LLMAgentBlock:
    return _make_llm(
        "landscape_planner",
        """You are a high-level strategic planner working within a specific software project.
You receive a user request (which includes the project name and path) and produce a GENERAL PANORAMA
that describes how to accomplish the request inside that project.

Your output must:
- List 3 to 7 main phases in logical order
- Name each phase with a short title
- Describe each phase in at most 2 lines (WHAT to do, not HOW)
- Refer to the project's existing structure when relevant (e.g. "extend the existing auth module")

CRITICAL RULES:
1. NEVER call any function or tool. Output PLAIN TEXT only.
2. NEVER create phases to "ask the user", "get preferences", or "wait for feedback". If details are missing, DO NOT ask questions. Instead, ASSUME a reasonable default approach and include it in the plan.
3. If the request is vague, fill in the blanks using industry best practices and proceed autonomously.
4. Phases are executed autonomously inside the project directory. Create only TECHNICAL IMPLEMENTATION
   phases (e.g. 'Add route handler', 'Update styles'). Include validation inside the same phase.
5. NEVER suggest creating a new project folder — the active project directory is always the workspace. Work inside it.

Output format:
1. [Phase Name]: [Brief description]
2. ...

Do not implement, do not detail, do not suggest code.
""",
        model=model,
    )


def make_refinement_agent(model: str | None = None) -> LLMAgentBlock:
    return _make_llm(
        "refinement_agent",
        """You refine an implementation plan based on user feedback, staying within the scope of the project.

Input:
ORIGINAL REQUEST: <request>
ORIGINAL PLAN: <plan>
USER FEEDBACK: <feedback>

Rules:
- Apply only the changes the user asked for. Do not restructure phases unrelated to the feedback.
- Keep the plan scoped to the active project directory. Never propose creating or moving to a new folder.
- Maintain the same output format as the original plan.

Output: the refined plan only. No preamble, no explanation.
""",
        model=model,
        disable_lang_rule=True,
    )
