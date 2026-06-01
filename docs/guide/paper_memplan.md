# MemPlan: A Memory-Augmented Planning Architecture for Autonomous Coding Agents on Small Language Models

**Gil Damasio**  
OpalaCoder Project — 2026

---

## Abstract

We present **MemPlan**, the cognitive architecture underlying OpalaCoder — an autonomous software engineering agent designed to operate primarily on small, locally-hosted language models (SLMs). MemPlan addresses the fundamental tension between the limited context windows and reasoning capacity of SLMs and the rich, multi-turn state required for non-trivial coding tasks. The architecture separates concerns across three layers: a **persistent memory layer** (MemGPT-style dual-role agent), an **intent classification layer** (context-enriched routing), and a **structured execution layer** (Python-driven Plan→Execute→Verify loop with reflection guardrails). We describe the design decisions behind each layer, the problems they solve, and the trade-offs involved in building a production coding agent that runs locally at near-zero cost.

---

## 1. Introduction

Large language models have demonstrated impressive capability for code generation, refactoring, and debugging. However, deploying these models at scale — particularly for individual developers who prefer local, private, low-latency environments — requires operating under significant constraints:

- **Context window limits**: Small models (7B–14B parameters) typically support 8k–32k tokens. A non-trivial project with multiple files, a conversation history, a task plan, and tool outputs can easily exhaust this budget.
- **Coherence degradation**: Performance of small models degrades sharply when context exceeds 60–70% of the nominal window. The model loses track of earlier instructions, repeats itself, or hallucinates tool calls.
- **Tool use reliability**: Small models trained primarily on text often revert to describing tool calls as plain JSON text rather than invoking the function calling API, especially when the number of registered tools is large or when a "thinking" mode (extended reasoning) is active.
- **Session continuity**: A developer's coding task rarely fits in a single turn. The agent must remember what was decided, what files were created, and what errors were encountered — across many separate invocations.

MemPlan is OpalaCoder's answer to these constraints. It does not attempt to solve them by using a larger model. Instead, it engineers the interaction protocol around the constraints of the small model.

---

## 2. Architecture Overview

MemPlan consists of three loosely-coupled layers, each with a distinct role:

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface (CLI)                  │
└────────────────────────┬────────────────────────────────┘
                         │ user message
                         ▼
┌─────────────────────────────────────────────────────────┐
│             Layer 1 — Memory & Routing                  │
│                                                         │
│  ┌──────────────────────┐   ┌─────────────────────┐    │
│  │  Enricher (Mode A)   │──▶│  Intent Classifier  │    │
│  │  MemGPT agent        │   │  (single-shot LLM)  │    │
│  │  reads core_memory   │   └─────────┬───────────┘    │
│  │  searches archival   │             │ intent label    │
│  └──────────────────────┘             │                 │
│                                       │                 │
│  ┌──────────────────────┐             │                 │
│  │  Synthesizer (Mode B)│◀────────────┘                 │
│  │  MemGPT agent        │  (chat/question intents)      │
│  │  writes core_memory  │                               │
│  │  speaks to user      │  (after orchestrator)         │
│  └──────────────────────┘                               │
└────────────────────────┬────────────────────────────────┘
                         │ plan / resume intents
                         ▼
┌─────────────────────────────────────────────────────────┐
│             Layer 2 — Planning                          │
│                                                         │
│  generate_panorama()  — landscape_planner agent         │
│  refine_plan()        — interactive user loop           │
│  plan.md saved to project directory                     │
└────────────────────────┬────────────────────────────────┘
                         │ approved plan
                         ▼
┌─────────────────────────────────────────────────────────┐
│             Layer 3 — Structured Execution              │
│                                                         │
│  Oracle (Planner)  ──▶ Task list (JSON, reflection)     │
│  Workers           ──▶ LLMAgentBlock × N (tool calls)  │
│  Oracle (Verifier) ──▶ reads real files on disk        │
│  Loop              ──▶ until done or heartbeat budget   │
└─────────────────────────────────────────────────────────┘
```

Each layer is described in detail in the sections that follow.

---

## 3. Layer 1 — Memory and Routing

### 3.1 The Dual-Role MemGPT Agent

The central cognitive entity in MemPlan is a single `OpalaMemGPTAgentBlock` instance — a MemGPT-style agent that maintains `internal_history` across turns within a session and has access to two memory stores:

- **Core Memory**: a short, structured text buffer (stored in SQLite) containing the most important persistent facts about the project: files created, architectural decisions, naming conventions, past errors. Read with `read_core_memory`, written with `append_core_memory`.
- **Archival Memory**: a ChromaDB vector database containing embeddings of all past conversations, execution logs, and orchestrator results. Queried with `search_conversation_history` using semantic similarity.

This agent is **instantiated once** per REPL session and kept alive across turns. Its `system_prompt` is switched dynamically before each `run()` call to change its role:

#### Mode A — Enricher

Before the intent classifier runs, the agent operates as an **Enricher**. Its task is not to answer the user — it is to produce a context-enriched version of the user's message for consumption by the classifier.

```
Input:  raw user message + project header
Output: original message + [CONTEXT] block from memory
```

The Enricher calls `read_core_memory` to load known project facts, and `search_conversation_history` when the message references past work ("fix the calculator", "continue what you did", "the error from before"). The output goes to the intent classifier, not to the user.

This design solves the amnesia problem: short, ambiguous messages like "fix it" or "implement the correction" carry enough context after enrichment for the classifier to correctly identify them as `plan` intents referencing a specific prior task.

#### Mode B — Synthesizer

After the orchestrator completes execution, or when the classifier routes to a conversational intent, the agent switches to **Synthesizer** mode. Here it:

1. Calls `append_core_memory` to persist newly learned facts (files created, patterns used, errors resolved).
2. Calls `send_message` to produce a user-facing summary in natural language.

The Synthesizer never echoes raw orchestrator output. It synthesizes — distilling a potentially long execution log into a concise, friendly message.

### 3.2 Intent Classification

The intent classifier is a lightweight, single-shot `LLMAgentBlock` configured with `think: false`, zero tools, and a small context window (2k tokens). It receives:

```
USER REQUEST: <original user message>
ENRICHED CONTEXT: <output from the Enricher>
```

And returns exactly one label from: `plan`, `resume`, `chat`, `question`, `greetings`, `command_hint`.

The use of enriched context is critical: the classifier is stateless and has no memory of its own. The Enricher acts as its memory proxy, injecting the relevant historical context that makes the classification unambiguous.

### 3.3 Routing Decision

| Intent | Action |
|--------|--------|
| `plan` | Human-in-the-loop planning → structured execution |
| `resume` | Reload last plan from SQLite → structured execution |
| `chat`, `question`, `greetings` | Switch agent to Mode B (Synthesizer) → respond to user |
| `command_hint` | Dispatch to CLI command registry |

---

## 4. Layer 2 — Planning

Planning is a two-phase human-in-the-loop process that runs before any code is written.

### 4.1 Phase 1 — Panorama Generation

A `landscape_planner` agent receives the enriched user request plus recent conversation history, and generates a natural-language implementation overview (the "panorama"). This is a high-level description of what will be built — not a task list, not code — expressed in terms a developer can read and evaluate.

The panorama is token-budget-aware: if the conversation history is too large for the model's context window, it is trimmed from the beginning (keeping the tail), preserving the most recent and most relevant context.

### 4.2 Phase 2 — Interactive Refinement

The panorama is shown to the user and saved to `plan.md` in the project directory. The user can:

- Press Enter to approve as-is
- Type feedback to request changes (the `refinement_agent` produces a revised plan)
- Type `/cancel` to abort and return to chat

Approval detection uses a fast heuristic path (word list matching) before falling back to a structured LLM classification via `instructor`. This avoids an unnecessary LLM round-trip for obvious cases ("sim", "ok", "yes").

The approved plan is persisted to `plan.md` and passed to the execution layer as a user-reviewed artifact.

---

## 5. Layer 3 — Structured Execution (WorkflowOrchestratorStrategy)

The execution layer implements the Plan→Execute→Verify loop described in specs3.md. Unlike the autonomous MemGPT orchestrator (which gives a single agent a long heartbeat budget and trusts it to self-direct), the workflow orchestrator is **Python-driven**: the loop, the decision to continue or stop, and the task decomposition are all controlled by Python code. The LLM is used only as a JSON oracle.

### 5.1 The Oracle

The oracle is a single `litellm.acompletion` call with `response_format: {"type": "json_object"}` — the only JSON mode reliably supported by Ollama. It is wrapped in a reflection guardrail that retries up to `MAX_REFLECT_RETRIES` times on JSON parse or schema validation failure, injecting the specific error message back into the conversation so the model can self-correct.

Two oracle types are used:

- **PlanOutput**: `{tasks: [{id, description}]}` — produces a list of fully self-contained task descriptions. Each description includes file paths, expected behavior, and relevant context, because workers share no memory between them.
- **VerifyOutput**: `{done, summary, corrections}` — evaluates whether the user's requirements are met, based on both the worker's self-reported result **and the actual file contents read from disk**.

Reading real file contents in the verify prompt is essential. Without it, the verifier can only evaluate the worker's self-report — which is unreliable when the worker fails silently (returning JSON-as-text instead of real tool calls).

### 5.2 Workers

Each task is executed by a dedicated `LLMAgentBlock` instance. Workers are configured with:

- `think: false` — prevents the gemma4 thinking mode from suppressing tool calls in `message.tool_calls`
- `max_tool_calls = sub_hb * 3` — allows enough tool invocations for multi-step tasks (read → edit → lint → verify)
- A curated tool set: `read_file`, `edit_file`, `find_symbol`, `write_file`, `run_command`, `search_code`, plus a `send_message` stub that signals task completion

The `edit_file` tool implements the **improvement loop** from specs3: it applies a find-replace edit atomically and immediately runs a syntax/lint check (`py_compile` for Python, `node --check` for JavaScript). If the check fails, the error is returned to the worker, which is expected to fix the specific line rather than rewrite the whole file.

The **decompose-on-failure** pattern (specs3): if a worker fails on the same file twice, a hint is appended to the error response instructing the model to identify and fix only the single failing line.

### 5.3 The Heartbeat Budget

The outer loop maintains a `heartbeats_used` counter. Each worker execution consumes one heartbeat. The loop terminates when:

- The verifier returns `done: true`
- The heartbeat budget is exhausted
- The verifier returns no corrections (ambiguous completion)

Correction tasks from the verifier are capped at 2 per cycle to prevent the budget from being consumed by a verifier that generates many redundant corrections in a single response.

### 5.4 Model Escalation

If a worker's result contains failure signals (`"error"`, `"failed"`, `"could not"`), the orchestrator automatically retries the same task with `ALTERNATIVE_MODEL` (e.g., a cloud-hosted model) if an API key is available. This implements the specs3 escalation rule: stay local 95% of the time, escalate to the cloud only for the 5% of tasks that the local model cannot handle.

---

## 6. Project-Centric Context Management

All three layers share a common abstraction: the **project**, not the session. Every interaction is anchored to a named project with a fixed filesystem path. This design decision has cascading benefits:

- **Stable context injection**: Every prompt receives a minimal `[PROJECT: name | PATH: /path]` header instead of a growing conversation blob. This keeps the prompt size predictable.
- **Tool path resolution**: All file operations resolve relative paths against `_PROJECT_PATH` — a module-level global set once at session start via `set_project_context()`. Workers never need to reason about absolute paths.
- **Skill scoping**: Skills (behavioral instructions injected as context) are selected at project creation and loaded per-project. The classifier and orchestrator only see skills relevant to the project type (e.g., `html_css_js` for frontend projects).
- **Persistence**: SQLite stores the project's history, plan state, core memory, and skill list. ChromaDB stores the archival embeddings. Both are keyed by project name.

---

## 7. Key Design Decisions

| Decision | Problem Solved | Trade-off |
|----------|---------------|-----------|
| Dual-role MemGPT agent (single instance, two prompts) | Session amnesia; classifier needs memory context without having its own state | Agent switches role mid-session; prompt must be carefully scoped to avoid mode leakage |
| Python-driven execution loop (oracle as JSON oracle) | Small models lose coherence after 3+ sequential tool calls; cannot self-direct a multi-file implementation | Removes agent autonomy from the execution layer; the Python loop must anticipate all control flow |
| Verifier reads actual file contents | Workers fail silently (returning JSON-as-text); self-reported results are unreliable | Increases verifier prompt size; must budget tokens carefully |
| `think: false` for workers | gemma4's thinking mode suppresses `message.tool_calls`; workers emit JSON descriptions instead of real tool calls | Disables extended reasoning for workers; they must be more explicit in task descriptions |
| `max_tool_calls = sub_hb * 3` | Default `max_tool_calls=2` caused workers to terminate before executing any real work | Large values risk runaway loops; capped by the outer heartbeat budget |
| Reflection guardrail in oracle | Small models frequently produce malformed JSON on first attempt | Each retry adds latency; at most `MAX_REFLECT_RETRIES` attempts before returning `None` |
| `send_message` stub in workflow tools | Worker system prompt trains on MemGPT conventions; model attempts to call `send_message` to signal completion | Stub must be present to prevent `tool not found` errors; its return value is ignored by the orchestrator |
| Correction cap (2 per verifier cycle) | Verifier can generate 4+ corrections per cycle, exhausting the heartbeat budget before meaningful work is done | Some corrections may be deferred to the next cycle |
| `system_plan`/`system_task` roles remapped to `assistant` | Legacy messages with invalid roles break LiteLLM's message validation | May cause minor semantic confusion in the chat agent's internal history |

---

## 8. Limitations and Future Work

**Tool call reliability**: The gemma4 model with Ollama occasionally reverts to generating JSON-as-text instead of invoking tools via the function calling API. This happens even with `think: false` when the model's context is large or the task description is ambiguous. A robust fix would require detecting this pattern in the worker result and injecting a correction prompt before terminating.

**Verifier false approvals**: When the verifier's JSON response truncates (due to `max_tokens`), the reflection guardrail's second attempt may generate a spurious `done: true` response. The current mitigation (explicitly forbidding approval without file evidence in the guardrail prompt) reduces but does not eliminate this.

**Core memory saturation**: The `append_core_memory` tool appends text indefinitely. As a project grows, core memory may become too large to inject efficiently. A future version should implement core memory summarization or eviction.

**Parallel worker execution**: The current implementation runs workers sequentially within each heartbeat cycle. For tasks with no data dependencies (e.g., creating three independent files), parallel execution would significantly reduce wall-clock time.

**Profile-based orchestration**: OpalaCoder includes a `ProfileExecutorStrategy` that builds a DAG from a YAML workflow definition. Integration with the MemPlan memory layer (so profiles can consult core memory and archival history) is not yet implemented.

---

## 9. Conclusion

MemPlan demonstrates that a capable autonomous coding agent does not require a frontier model or an unbounded context window. By separating memory management, intent routing, planning, and execution into distinct layers — each engineered around the specific failure modes of small language models — OpalaCoder achieves robust multi-turn coding assistance on locally-hosted 7B–14B parameter models.

The key insight is that **the most important variable is not the model's capability, but the structure of the information it receives at each step**. A small model given a precise, memory-enriched, token-budgeted prompt with a clear output schema consistently outperforms a larger model given an unbounded, history-laden, open-ended prompt.

---

## References

- Packer, C. et al. (2023). *MemGPT: Towards LLMs as Operating Systems*. arXiv:2310.08560.
- OpalaCoder specs3.md — internal specification for composite tools, improvement loop, and escalation strategy.
- LiteLLM documentation — `response_format`, Ollama JSON mode, tool calling.
- AgenticBlocks.IO framework — `LLMAgentBlock`, `OpalaMemGPTAgentBlock`, `FunctionBlock`, A2A bridge.
