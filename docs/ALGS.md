# OpalaCoder Algorithms

This document describes the core algorithmic logic and decision flows adopted in OpalaCoder's architecture.

## 1. Structured Task Decomposition with Semantic Reflection

### Motivation

Small language models (Gemma 4, Mistral-Nemo) degrade on multi-file tasks when the planner emits vague task descriptions. A worker given only `"Create style.css"` has no knowledge of which HTML classes to target, what IDs the JS must wire up, or which files are the source of truth. The result is hallucinated content that is syntactically valid but semantically disconnected from the rest of the project.

The core insight is: **workers share no memory between tasks**. All context required for a task must be explicitly encoded in its description. The planner must be forced — not just instructed — to provide that context.

### The Structured Task Schema

Every task the planner emits is validated against a Pydantic schema before reaching any worker:

```python
class Task(BaseModel):
    id: str             # short unique identifier (t1, t2, ...)
    goal: str           # one sentence: what this task achieves and WHY
    commands: list[str] # ordered atomic steps; each runs as a separate worker call
    related_files: list[str]  # files the worker must read before acting
    context: str        # operational detail: class names, IDs, APIs, file contracts
    depends_on: list[str]     # explicit ordering between tasks
```

This replaces the previous monolithic `description: str` field, which provided no structural guarantee that the worker had sufficient context.

### Semantic Validation (`_validate_task`)

After structural JSON parsing and Pydantic validation succeed, the oracle runs a semantic check on every task in the plan:

| Condition | Rejection reason |
|---|---|
| `goal` is blank | Worker cannot infer what the task is for |
| `commands` is empty | No actionable steps — worker has nothing to execute |
| `context` is blank | Worker must guess cross-file contracts (class names, IDs, APIs) |
| CSS/JS task with empty `related_files` | Worker cannot know which selectors or element IDs to target |

When validation fails, the oracle injects a specific, structured error message back into the conversation and retries — up to `MAX_REFLECT_RETRIES` times:

```
[GUARDRAIL]: Plan tasks are incomplete:
task 't2': 'context' is empty — provide operational details
  (class names, function signatures, IDs, contracts with other files).
task 't2': 'related_files' is empty for a CSS/JS task — list the HTML or
  source files that define the classes/IDs being targeted.
Fix ALL flagged tasks before returning the plan.
```

This differs from structural reflection (which recovers from malformed JSON) in that it encodes **domain knowledge** about what makes a task executable: a CSS worker without HTML class names will fail regardless of syntactic validity.

### Worker Execution: Per-Command Context Injection

Each task's `commands` list is executed sequentially. Every command runs as a separate `LLMAgentBlock` call. Before the command text, a structured preamble is injected:

```
TASK GOAL: Create style.css to style the calculator layout in index.html
RELATED FILES (read these first): index.html
CONTEXT:
index.html uses: .calculator (flex wrapper, 280px), .display (output, 2rem),
.buttons (4-column grid), .btn (base), .btn-clear/.btn-number/.btn-equals (variants).
Button IDs: clear, 7, add, equals.
---
COMMAND: Create style.css with CSS reset and .calculator wrapper styles
```

This preamble is injected by the orchestrator — not the LLM — so it is guaranteed to be present regardless of how the model responds. The worker never needs to infer contracts by reading cross-file relationships; all necessary information arrives in the prompt.

### Lint-Driven Self-Correction

Both `edit_file` and `write_file` run `_auto_lint()` after every write. Syntax errors are returned as tool output (not raised as exceptions), so the worker's reflection loop receives them and self-corrects:

```
Successfully wrote to script.js, but lint check found errors:
/path/script.js:135
SyntaxError: Unexpected token '}'
Please fix the syntax errors.
```

Without this, a worker that writes broken code has no signal to retry. With it, the correction happens within the same `LLMAgentBlock` run, before `send_message` is called.

### Full Reflection Stack

The oracle loop handles three distinct failure modes, each with its own feedback injection:

1. **JSON syntax error** — `json.JSONDecodeError`: inject parse error, retry
2. **Schema validation error** — Pydantic `ValidationError`: inject field-level error, retry
3. **Semantic validation error** — `_validate_task()`: inject domain-specific feedback per field, retry

All three share the same retry budget (`MAX_REFLECT_RETRIES = 3`) and message injection pattern.

---

## 2. Double Inference Complexity Algorithm and Dynamic Budgeting

OpalaCoder implements an innovative model known as **Two-Stage Predictive Budgeting** to ensure maximum financial and resolutive efficiency for LLM agents. The goal of this algorithm is to avoid wasting tokens from expensive models on initial planning if the task is trivial, but without compromising the execution if the detailed plan reveals architectural complexities.

The execution is controlled by the `complexity_inference_mode` configuration located in `agents.yaml`, operating in either `simple` or `double` modes.

### Logic Flow (`double` mode)

The algorithm follows these procedural steps:

1. **First Stage: Pre-Plan Heuristic Inference (Strategy 1)**
   - The user submits a prompt with their original request.
   - The `make_complexity_evaluator` receives this raw request and returns one of two complexity labels: `"default"` or `"alternative"`.
   - Based on this label, OpalaCoder chooses the base model that will generate the "Landscape" (Phase 1) and conduct the interactive Refinement (Phase 2).
   - *Purpose:* Ensure that the initial cognitive capacity of the planner is equivalent to the presumed complexity by the user, saving excessive processing on short and simple requests.

2. **Plan Refinement Loop**
   - The plan goes through interactive cycles of human approval. The final outcome of this step is the `approved_plan` text.

3. **Second Stage: Post-Plan JSON Evaluation (Strategy 3)**
   - Instead of jumping straight to execution (as competing agents would do), OpalaCoder intercepts the pipeline before the orchestrator initializes.
   - The `make_post_plan_evaluator` reads the final `approved_plan` line by line.
   - The expected output from this agent is a strict JSON format:
     ```json
     {
       "model": "default | alternative",
       "estimated_steps": <integer>
     }
     ```
   - *Execution Promotion Analysis (`model`)*: The algorithm compares the orchestrator's current model with the JSON prediction. If the JSON concludes that the architecture outlined in the plan is more complex than it seemed in the prompt (requiring `"alternative"`) and the orchestrator was set to `"default"`, the algorithm **upgrades (promotes)** the orchestrator to the alternative model *in-flight*, guaranteeing deep reasoning power for the most critical stage.
   - *Budget Calculation (`max_heartbeats == "auto"`)*: If the orchestration config dictates static heartbeats, nothing changes. However, if it is set to `"auto"`, the ceiling calculation takes effect:
     ```python
     max_hb_config = min(estimated_steps * 3 + 5, 200)
     ```
     The estimated number of steps (e.g., read_file, write_file, run_command) semantically extracted by the LLM is multiplied by a safety margin (3) plus a fixed delta (5), always capped by the maximum logical limit (200), preventing infinite hallucination loops.

4. **Execution**
   - The `AutonomousOrchestratorStrategy` inherits the readjusted `model` and the organically calculated `max_heartbeats`, and triggers the MemGPT instances.

### Fallback Mode (`simple` mode)
If the configuration is set to `simple` or if the JSON Extraction of the *Post-Plan Evaluator* fails due to formatting hallucination:
- In-flight model promotion is ignored.
- If heartbeats are set to `"auto"`, a static contingency ceiling of `max_hb_config = 50` is applied.
