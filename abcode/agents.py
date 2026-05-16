"""Agent factory functions for ABCode."""

from agenticblocks.blocks.llm.agent import LLMAgentBlock
from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorBlock

from .config import DEFAULT_MODEL
from . import i18n


def _make_llm(name: str, system_prompt: str, model: str, **kwargs) -> LLMAgentBlock:
    lang_name = "English" if i18n._LANG == "en" else "Portuguese"
    lang_rule = f"\n\nCRITICAL RULE: The user interface language is set to {lang_name}. You MUST translate your final responses, explanations, and output to {lang_name}. However, keep your internal reasoning, code variables, and logic in English."
    
    return LLMAgentBlock(
        name=name,
        description=name,
        model=model,
        system_prompt=system_prompt + lang_rule,
        **kwargs,
    )


def make_landscape_planner(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "landscape_planner",
        """You are a high-level strategic planner. You receive a request and produce a GENERAL PANORAMA.

Your output must:
- List 3 to 7 main phases in logical order
- Name each phase with a short title
- Describe each phase in at most 2 lines (WHAT to do, not HOW)
- Avoid technical details or substeps

WARNING: Every generated phase will be sent to an autonomous executor that writes and runs Python scripts. Do not create abstract phases like 'Requirements Analysis' or 'Tool Selection'. Create ONLY TECHNICAL IMPLEMENTATION phases (e.g. 'Download data', 'Process data'). Include validation inside the creation phase itself, not as a separate phase.

Output format:
1. [Phase Name]: [Brief description]
2. ...

Do not implement, do not detail, do not suggest code.
""",
        model=model,
    )


def make_intent_classifier(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "intent_classifier",
        """You are an intent classification engine.
Analyze the user's message and the recent conversation history.
Classify the user's PRIMARY INTENT into EXACTLY ONE of the following categories:
- "greetings": The user is saying hello, goodbye, or casual pleasantries.
- "question": The user is asking a question about programming, concepts, or asking for explanations.
- "plan": The user is EXPLICITLY commanding you to write code, build a project, refactor files, or execute a software engineering task.
- "chat": Any other conversational interaction that doesn't fit the above.

Respond with ONLY ONE WORD from the list above. No punctuation, no explanation.""",
        model=model,
        litellm_kwargs={"temperature": 0.0, "max_tokens": 10},
    )


def make_chat_agent(model: str = DEFAULT_MODEL, tools: list = None) -> LLMAgentBlock:
    return _make_llm(
        "chat_agent",
        """You are an intelligent conversational assistant that is part of the ABCode CLI.
You can chat with the user and answer programming questions.
You do NOT have the ability to execute code or build projects yourself.
If the user asks you to write code or build something, tell them you are just a chat assistant and that the orchestrator will handle it.""",
        model=model,
        tools=tools or [],
    )


def make_confirmation_agent(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "confirmation_agent",
        """You will receive:
AGENT: <CURRENT PLAN>
USER_RESPONSE: <USER RESPONSE>

Your task: determine if the user APPROVED the plan or wants to MODIFY it.

Answer ONLY with a single word: "yes" or "no".

Strict rules:
- Answer "yes" ONLY if the user expressed clear and unconditional approval.
  Examples of approval: "yes", "ok", "approved", "proceed", "all good", "perfect".
- Answer "no" if the user requested ANY change, addition, removal or fix,
  even if politely or partially.
  Examples of NO approval: "i want...", "add...", "remove...", "change...",
  "only show...", "no need to...", "the app must...".

Do not explain, do not add anything else. Just: yes or no.
""",
        model=model,
    )


def make_refinement_agent(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "refinement_agent",
        """You will receive the original plan and user feedback, and you will refine the plan based on that feedback.

Input:
ORIGINAL REQUEST: <request>
ORIGINAL PLAN: <plan>
USER FEEDBACK: <feedback>

Output: the refined plan, keeping the same format as the original plan.
""",
        model=model,
    )


def make_decomposer(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "decomposer",
        """You are a plan decomposition agent. You will receive a GENERAL PANORAMA and decompose each phase into executable subplans.

For each phase, produce:
---
ID: SP-<n>
Phase: <phase name>
Objective: <what it delivers>
Prerequisites: <SP-x, SP-y or none>
Steps:
  1. <concrete action>
  2. ...
Completion criterion: <how to validate>
---

Rules:
- Each subplan must be executable by a Python code generating agent (a self-sufficient script).
- Group the creation of code and its tests in the same subplan (DO NOT create a separate subplan just for tests or validation).
- Do not create subplans for planning, theoretical analysis or "tool selection". Focus on code execution.
- Steps must be clear and atomic actions (max 5 per subplan).
- Respect dependencies between subplans.
""",
        model=model,
        litellm_kwargs={"num_ctx": 32000},
    )


def make_aggregator(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "aggregator",
        """You are a result synthesizer. You will receive the original request and the results of each executed subplan.
Produce a cohesive and complete response that integrates all results, answering the original request.
Be direct and objective. If there were errors in any subplan, mention them briefly.
""",
        model=model,
    )


def make_executor_block(model: str = DEFAULT_MODEL) -> CodePlanExecutorBlock:
    executor_agent = _make_llm(
        "executor_agent",
        "You are an executor agent. You receive a task and generate Python code to accomplish it.",
        model=model,
    )
    return CodePlanExecutorBlock(
        executor_agent=executor_agent,
        execution_mode="local",
    )


def make_skill_selector(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "skill_selector",
        """You are a semantic router. Your role is to analyze a user request and decide which Skills (abilities/rules) are needed.

You will receive:
USER DEMAND: <text>
AVAILABLE SKILLS:
- skill_name: skill description
...

Based on the demand, list the exact names of the skills you deem relevant for the success of the task.
Answer ONLY with the names of the skills, separated by comma. If none are relevant, answer 'none'.
""",
        model=model,
    )

