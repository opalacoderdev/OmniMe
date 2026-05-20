# OpalaCoder — Core Algorithms and Decision Flows

This document describes the algorithmic strategies adopted in OpalaCoder, from user input to plan execution and verification.

---

## 1. Request Enrichment Before Classification

### Problem

The intent classifier receives raw user input. Short or ambiguous messages ("continue", "fix it", "change the color") are systematically misclassified without context. A history dump is noisy and causes the planner to act on unrelated prior tasks.

### Solution: Two-Stage Enrichment

Before classification, the `chat_agent` runs in **Mode A (enricher)** — a silent pass that never reaches the user. Its system prompt instructs it to retrieve relevant memory and reformulate the request with project context:

```
repl_loop()
  │
  ├─ chat_agent (Mode A — enricher)
  │    input:  user_input + project header
  │    output: enriched_output  (relevant context extracted from memory)
  │    → never shown to the user
  │
  ├─ intent_classifier
  │    input:  "USER REQUEST: {user_input}\nENRICHED CONTEXT: {enriched_output}"
  │    output: plan | question | chat | greetings | resume | command_hint
  │
  └─ if intent == "plan":
       augmented_request = "Original Request: {user_input}\nMemory Context:\n{enriched_output}"
       run_pipeline(request=augmented_request)
```

The `augmented_request` carries the enriched context all the way into the planner. The planner therefore receives a self-contained, context-enriched request — without raw history.

### Why not pass raw history to the planner?

Passing the last N messages to the planner caused it to act on unrelated prior tasks. For example, a request to "change the background color" would produce a plan that also attempted to fix bugs mentioned in an earlier exchange. The enricher solves this by filtering: only information that is semantically relevant to the current request is forwarded.

---

## 2. Intent Classification

The classifier is a single-shot `LLMAgentBlock` with `reasoning_effort: "none"` (tool calls are empty when thinking is enabled on Ollama models). It receives the enriched prompt and returns exactly one word:

| Intent | Meaning |
|---|---|
| `plan` | A concrete change to files on disk is requested |
| `question` | Information, explanation, or project status is requested — nothing to execute |
| `chat` | Conversational message with no programming task |
| `greetings` | Hello, goodbye, casual pleasantry |
| `resume` | Continue or finish a previously interrupted plan |
| `command_hint` | Entire message is a CLI command word (clear, list, help, …) |

Key rule added to the prompt: questions about project history or status ("what have we done so far?", "what is the current status?") are `question`, never `plan`.

---

## 3. Plan → Execute → Verify Loop

The `WorkflowOrchestratorStrategy` drives execution entirely in Python. The LLM acts as a JSON oracle — it never runs tools in the planning or verification phases.

```
WorkflowOrchestratorStrategy.run(augmented_request)
  │
  ├─ set_project_context()          ← must run first; sets get_project_path()
  ├─ _plan_and_refine()             ← panorama + user approval loop
  ├─ VCS auto-checkpoint            ← shadow git commit before any file is touched
  ├─ code index build               ← incremental symbol index for the project
  │
  └─ _orchestration_loop()
       │
       ├─ PHASE 1 — PLAN
       │    _oracle(PlanOutput)     ← decomposes augmented_request into Tasks
       │    _validate_task()        ← semantic guardrail (see §4)
       │    reflection on failure   ← up to MAX_REFLECT_RETRIES
       │
       ├─ PHASE 2 — EXECUTE  (for each pending Task)
       │    for each command in task.commands:
       │      LLMAgentBlock(
       │        prompt = context_block + command,
       │        termination_tools = ["send_message"]   ← stops immediately on call
       │      )
       │      worker calls: read_file, edit_file, write_file,
       │                    find_symbol, run_command, send_message
       │      edit_file / write_file → _auto_lint() → lint errors fed back to worker
       │
       └─ PHASE 3 — VERIFY
            _oracle(VerifyOutput)   ← reads actual file contents on disk
            done=True  → mark task done, advance
            done=False → inject correction Tasks → back to PHASE 2
```

---

## 4. Structured Task Schema and Semantic Validation

### Problem

Workers share no memory between tasks. A worker given only `"Create style.css"` has no knowledge of which HTML classes to target. The result is syntactically valid but semantically disconnected output.

### The Task Schema

Every task is validated against a Pydantic schema before reaching any worker:

```python
class Task(BaseModel):
    id: str              # short unique identifier (t1, t2, ...)
    goal: str            # one sentence: what this task achieves and WHY
    commands: list[str]  # ordered atomic steps; each runs as a separate worker call
    related_files: list[str]  # files the worker must read before acting
    context: str         # operational detail: class names, IDs, APIs, contracts
    depends_on: list[str]     # explicit ordering between tasks

    @field_validator("context", mode="before")
    def _coerce_context(cls, v):
        # coerces dict/list → JSON string for models that emit object-typed context
        return json.dumps(v) if not isinstance(v, str) else v
```

### Semantic Validation (`_validate_task`)

After structural validation, a semantic check runs on every task:

| Condition | Rejection reason |
|---|---|
| `goal` is blank | Worker cannot infer what the task is for |
| `commands` is empty | No actionable steps |
| `context` is blank | Worker must guess cross-file contracts |
| CSS/JS task with empty `related_files` | Worker cannot know which selectors or IDs to target |

Failures inject specific feedback into the oracle conversation and retry up to `MAX_REFLECT_RETRIES` times.

### Context Block Injection

Every worker call receives a structured preamble before the command text:

```
TASK GOAL: Create style.css to style the calculator layout defined in index.html

RELATED FILES (read these first):
- index.html

CONTEXT:
index.html uses: .calculator (flex wrapper), .display (output, 2rem),
.buttons (4-column grid). Button IDs: clear, equals, add.

COMMAND: Create style.css with CSS reset and .calculator wrapper styles
```

This preamble is injected by the orchestrator — not the LLM — so it is guaranteed to be present regardless of model behavior.

### Hard Rules in the Planner System Prompt

Certain fix patterns are explicitly encoded to prevent common model errors:

- **Redeclaration errors**: fix = delete the duplicate line using `edit_file(old_str=<line>, new_str="", line=N)`. Never change `const` → `let` — that keeps the duplicate.
- **`edit_file` `line` param**: when `old_str` appears more than once, supply the `line` parameter (1-based) to target the occurrence closest to that line number.

---

## 5. Worker Termination via `termination_tools`

### Problem

`LLMAgentBlock` has no native concept of "done". Without an explicit stop signal, the worker loop continues after `send_message` is called, potentially introducing new bugs before the next iteration receives control.

### Solution

`LLMAgentBlock` is initialized with `termination_tools=["send_message"]`. When the worker calls `send_message`, the agenticblocks runtime returns `AgentOutput` immediately — the loop never continues past that call.

This requires agenticblocks ≥ commit `98795f3` (feat: support termination tools).

---

## 6. Lint-Driven Self-Correction

Both `edit_file` and `write_file` call `_auto_lint()` after every write:

- `.py` → `py_compile`
- `.js` / `.ts` / `.jsx` / `.tsx` → `node --check`

Syntax errors are returned as tool output (not raised as exceptions), so the worker's reflection loop receives them as feedback and self-corrects within the same `LLMAgentBlock` run, before `send_message` is called.

---

## 7. Oracle Reflection Stack

The oracle loop handles three distinct failure modes:

| Failure | Source | Feedback injected |
|---|---|---|
| JSON syntax error | `json.JSONDecodeError` | Parse error with position |
| Schema validation | Pydantic `ValidationError` | Field name + error message |
| Semantic validation | `_validate_task()` | Domain-specific feedback per field |

All three share the same retry budget (`MAX_REFLECT_RETRIES = 3`) and message injection pattern. The oracle uses `response_format={"type": "json_object"}` — the only JSON mode Ollama reliably supports for small models.

---

## 8. Shadow VCS and `/undo`

### Checkpoint Flow

```
set_project_context()         ← must run first (fixes get_project_path())
_vcs.setup()                  ← initializes .opalacoder/.git if absent
_vcs.manual_commit(           ← commits current state before any worker runs
  "auto-checkpoint before plan execution"
)
```

The checkpoint runs **after** `set_project_context()` so `get_project_path()` returns the user's project path, not OpalaCoder's own root. All `_run_shadow_git` calls receive `project_path` explicitly — never rely on the global.

### `/undo`

```
vcs.undo_last()
  → git --git-dir=.opalacoder/.git --work-tree=<project> reset --hard HEAD~1
  → git clean -fd
```

Requires at least 2 commits in the shadow git (initial + pre-execution checkpoint). Returns `"Cannot undo. No previous checkpoints."` if only the initial commit exists.

---

## 9. Complexity Evaluation and Dynamic Model Selection

```
if model.startswith("ollama/"):
    # heuristic: long requests are complex
    complexity = "alternative" if len(user_input.split()) > 200 else "default"
else:
    # LLM evaluator for hosted models
    complexity_evaluator.run(user_input) → "default" | "alternative"

if complexity == "alternative":
    active_model = ALTERNATIVE_MODEL   # from agents.yaml
else:
    active_model = project.model
```

Both `default` and `alternative` are configured in `agents.yaml`. Currently both point to `ollama/ministral-3:14b`; the alternative can be set to a hosted model (e.g. `gemini/gemini-2.0-flash`) when an API key is available.

---

## 10. Code Index

A multi-language symbol index (SQLite-backed) is built incrementally before each orchestration run:

- **`build()`** — scans all files, skips unchanged ones by mtime
- **`rebuild_file(path)`** — called automatically by `edit_file` and `write_file`
- **`search(query)`** — exact → prefix → substring match
- **`find_callers(name)`** — reverse call graph
- **`project_snapshot()`** — symbol-enriched file listing fed to oracle prompts

The snapshot gives the planner function-level granularity when decomposing tasks, instead of a plain file list.
