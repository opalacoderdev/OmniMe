"""Agent factory functions for OpalaCoder."""

from agenticblocks.blocks.llm.agent import LLMAgentBlock, AgentInput
from agenticblocks.blocks.llm.memgpt_agent import MemGPTAgentBlock

from .config import DEFAULT_MODEL, LITELLM_DEFAULTS, get_agent_llm_kwargs, get_agent_model, get_agent_max_heartbeats, get_agent_debug
from . import i18n

def _make_llm(name: str, system_prompt: str, model: str | None, disable_lang_rule: bool = False, **kwargs) -> LLMAgentBlock:
    lang_name = "English" if i18n._LANG == "en" else "Portuguese"
    lang_rule = ""
    if not disable_lang_rule:
        lang_rule = f"\n\nCRITICAL RULE: The user interface language is set to {lang_name}. You MUST translate your final responses, explanations, and output to {lang_name}. However, keep your internal reasoning, code variables, and logic in English."

    resolved_model = get_agent_model(name, model or DEFAULT_MODEL)

    # Start from per-agent config, then apply any explicit caller overrides (caller wins)
    merged_kwargs = {**get_agent_llm_kwargs(name), **kwargs.get("litellm_kwargs", {})}
    kwargs["litellm_kwargs"] = merged_kwargs

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


def make_intent_classifier(model: str | None = None) -> LLMAgentBlock:
    return _make_llm(
        "intent_classifier",
        """You are a strict intent router. Your job is to classify the USER REQUEST.
You will also receive RECENT CONTEXT (last 3 messages) to help you understand ambiguous requests (like "continue" or "fix it").

Classify the USER REQUEST into EXACTLY ONE of these categories: below.
Read each category carefully — they have clear, non-overlapping definitions.

- "command_hint": The user's ENTIRE message is exactly one of these CLI command words,
  optionally followed by arguments: clear, help, exit, quit, rename, list, load, delete,
  skills, lsskills, addskill, rmskill.
  The message contains NOTHING else — no question, no programming request, no context.
  Examples: "clear", "exit", "rename myproject", "addskill python".

- "greetings": The user is saying hello, goodbye, or exchanging casual pleasantries.
  No task is being requested.
  Examples: "hi", "thanks", "bye", "good morning".

- "question": The user is asking for an explanation, concept clarification, or information
  about code — WITHOUT requesting that anything be written, changed, or executed.
  Examples: "what does async mean?", "how does this function work?".

- "plan": The user wants a COMPLETELY NEW feature, project, or bug fix to be built, changed, or deleted on disk.
  Examples: "create a calculator", "fix the login bug", "add a dark mode".

- "resume": The user explicitly asks to continue, resume, finish, or keep going with the PREVIOUS or CURRENT plan that was interrupted or left halfway.
  Examples: "continue o que tinha feito antes", "resume the plan", "keep going", "finish it".

- "chat": A conversational message with no programming task implied — opinions, jokes,
  philosophical discussion, follow-up small talk.
  Examples: "that's interesting", "I don't like Python", "what do you think about AI?".

Respond with ONLY ONE WORD from the list: command_hint, greetings, question, plan, resume, chat.
No punctuation, no explanation.""",
        model=model,
        disable_lang_rule=True,
    )

def make_complexity_evaluator(model: str | None = None) -> LLMAgentBlock:
    return _make_llm(
        "complexity_evaluator",
        """You are a complexity evaluation engine.
Analyze the user's request. Does it require simple file edits, quick answers, or routine commands? Or does it require complex architectural changes, deep reasoning, extensive multi-file refactoring, or advanced coding logic?

Classify the user's request complexity into EXACTLY ONE of the following categories:
- "default": The task is simple, straightforward, and can be handled by a standard fast model.
- "alternative": The task is highly complex, involves heavy refactoring, or requires an advanced reasoning model.

Respond with ONLY ONE WORD from the list above. No punctuation, no explanation.""",
        model=model,
        disable_lang_rule=True,
    )


def make_post_plan_evaluator(model: str | None = None) -> LLMAgentBlock:
    return _make_llm(
        "post_plan_evaluator",
        """You evaluate a finalized implementation plan to calculate the expected execution effort.
You will receive the full text of an APPROVED PLAN.

Your task is to analyze the steps, the scope of file modifications, and the logic required.
Then output a JSON object with exactly two keys:
1. "model": Choose "default" if the steps are standard, straightforward coding tasks. Choose "alternative" if the plan involves deep refactoring, new complex algorithms, heavy debugging, or high risk.
2. "estimated_steps": An integer representing how many distinct actions/tools the agent might realistically need to run to finish this entire plan. E.g., reading a file is 1 step, writing is 1 step, running tests is 1 step. Be slightly pessimistic (overestimate).

Output ONLY valid JSON. No markdown formatting, no comments, no extra text.
Example: {"model": "default", "estimated_steps": 12}
""",
        model=model,
        disable_lang_rule=True,
        litellm_kwargs={"response_format": {"type": "json_object"}}
    )


def make_chat_memgpt_agent(model: str | None = None) -> MemGPTAgentBlock:
    """Create a MemGPT chat agent that maintains conversation history internally.

    The returned instance should be kept alive for the duration of a project REPL loop
    so that its internal memory persists across turns.
    """
    lang_name = "English" if i18n._LANG == "en" else "Portuguese"
    lang_rule = (
        f"\n\nCRITICAL RULE: Respond in {lang_name}. "
        "Keep code identifiers in English."
    )

    from .tools import read_core_memory, append_core_memory, search_conversation_history
    
    system_prompt = (
        "You are OpalaCoder's conversational assistant, embedded inside a software project.\n"
        "You operate using a MemGPT-style memory hierarchy:\n"
        "1. **Core Memory**: Fast, persistent storage for crucial facts about the user and the project. You can read/write to it using `read_core_memory` and `append_core_memory`.\n"
        "2. **Archival Memory**: An infinite, searchable vector database of all past conversations, executed plans, and system logs. You MUST use `search_conversation_history` to retrieve past context if the user asks you to 'continue', refers to 'what we were doing', or asks about a past error/plan.\n\n"
        "You do NOT build or execute projects; that is handled by the autonomous orchestrator "
        "when the user explicitly requests a plan execution.\n"
        "When the user mentions past events, always search your archival memory before answering.\n"
        "Be concise, friendly, and precise."
        + lang_rule
    )

    return MemGPTAgentBlock(
        name="chat_agent",
        system_prompt=system_prompt,
        model=get_agent_model("chat_agent", model or DEFAULT_MODEL),
        tools=[read_core_memory, append_core_memory, search_conversation_history],
        litellm_kwargs=get_agent_llm_kwargs("chat_agent"),
        max_heartbeats=get_agent_max_heartbeats("chat_agent", 10),
        debug=get_agent_debug("chat_agent", False),
    )


def make_confirmation_agent(model: str | None = None) -> LLMAgentBlock:
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
        disable_lang_rule=True,
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


def make_skill_selector(model: str | None = None) -> LLMAgentBlock:
    return _make_llm(
        "skill_selector",
        """You are a semantic router. Your role is to analyze a user request and decide which Skills (abilities/rules) are needed.

You will receive:
USER REQUEST: <text>
AVAILABLE SKILLS:
- skill_name: skill description
...

Step 1: Internally translate the user demand to English to understand exactly what is being asked.
Step 2: Based on the translated demand, list the exact names of the skills you deem relevant for the success of the task.

Answer ONLY with the names of the skills, separated by comma. If none are relevant, answer 'none'.

CRITICAL RULES:
1. If the user demand is a single word without context or meaningless (e.g. "list", "help", "hello"), you MUST include the 'opalacoder' skill.
2. NEVER select a framework skill (like `react_vite`) if the user requests "plain", "vanilla", or "manually" created files, or explicitly says "without react".
3. ONLY select skills whose description perfectly matches the requested technologies.
""",
        model=model,
        disable_lang_rule=True,
    )
