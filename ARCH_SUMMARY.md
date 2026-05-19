# OpalaCoder — Architecture Summary

## Focus

OpalaCoder is designed to work with **small language models** (e.g. Gemma 4, Mistral-Nemo via Ollama) as its primary target. Large models (Gemini, GPT-4, Claude) are supported as a fallback for complex tasks, but the core design prioritizes correctness and usability under constrained context windows and limited reasoning capacity.

## Core Idea: Project-Centric Context Management

The central abstraction is the **project**, not the session. Every interaction happens within a named project that has a fixed filesystem path. This design decision exists for one reason: **context management**.

Small models degrade quickly when context is large, mixed, or unbounded. By anchoring all activity to a project, OpalaCoder can:

- Inject a stable, minimal project header (`[PROJECT: name | PATH: /path]`) into every prompt instead of growing conversation state
- Load only the skills relevant to that project type (selected at creation, not dynamically per-request)
- Scope all file reads, writes, and commands to the project directory, eliminating ambiguity about where things should go
- Persist history, plan state, and skill configuration per project in SQLite, keeping each LLM call focused

## Architecture

```
CLI (cli.py)
 ├── startup_menu()          — load or create project
 ├── _create_project()       — name + path + description → LLM selects skills
 └── repl_loop()             — main REPL; loads project-scoped skills once
      ├── REPLState           — session container; holds chat_agent, intent_classifier,
      │                         complexity_evaluator (created once, reused per turn)
      ├── run_pipeline()      — triggers orchestration for planning tasks
      │    └── get_orchestrator(strategy)     — reads strategy from agents.yaml,
      │         └── OrchestratorRegistry      looks up registered class, instantiates it
      │              └── WorkflowOrchestratorStrategy  (default: strategy: workflow)
      │                   ├── _plan_and_refine()    phase 1+2: panorama + user refinement
      │                   └── _orchestration_loop() phase 3: Plan→Execute→Verify
      │                        ├── _oracle(PlanOutput)   — task decomposition
      │                        ├── _run_worker(task)     — per-command LLMAgentBlock
      │                        └── _oracle(VerifyOutput) — acceptance check
      └── chat_agent          — conversational assistant with memory

Orchestrator Registry (orchestrator.py)
 ├── register_orchestrator(name)  — class decorator; maps name → strategy class
 ├── get_orchestrator(name, model)— instantiates registered strategy; raises ValueError
 │                                  for unknown names (fails loudly on misconfiguration)
 ├── CHECKPOINT_SUBPATH           — shared constant ".opalacoder/session_state.json"
 └── BaseOrchestratorStrategy     — abstract base; subclasses implement run()

WorkflowOrchestratorStrategy (workflow_orchestrator.py)
 ├── Task schema (Pydantic)
 │    ├── id             — short unique identifier (t1, t2, ...)
 │    ├── goal           — one-sentence objective: what + why
 │    ├── commands       — ordered list of atomic worker steps
 │    ├── related_files  — files worker must read before acting
 │    ├── context        — operational detail: class names, IDs, APIs, contracts
 │    └── depends_on     — explicit ordering between tasks
 ├── _validate_task()     — semantic guardrail: rejects empty goal/commands/context
 │                          and CSS/JS tasks without related_files
 ├── _oracle()            — litellm call with JSON mode + structural + semantic reflection
 ├── _run_worker()        — iterates task.commands; each command = one LLMAgentBlock call
 │                          with context_block preamble (TASK GOAL / RELATED FILES /
 │                          CONTEXT / COMMAND) injected into every worker prompt
 └── _planner_system()    — system prompt with full Task schema + field rules + examples

Project (project.py)
 ├── ProjectData             — name, path, skills, description, history, plan state
 └── ProjectStore            — SQLite CRUD for projects and message history

Skills (skills.py)
 ├── load_project_skills()   — loads only skills listed in the project
 ├── select_skills_for_project() — LLM picks skills from description at creation
 ├── find_skill_file()       — resolves <name>.md across skill search dirs
 └── get_relevant_skills_llm()  — semantic router (uses project skills only)

Tools (tools.py)              — file read/write, run_command, search_code, ask_human
 ├── _PROJECT_PATH global    — all tools resolve paths relative to the project dir
 ├── write_file              — writes file + runs _auto_lint(); returns lint errors
 │                             to worker so reflection loop can self-correct
 └── _auto_lint()            — py_compile for .py, node --check for .js/.ts/.jsx/.tsx

Workflow Tools (workflow_tools.py)
 ├── find_symbol              — index-backed, all languages, falls back to grep
 ├── find_callers             — reverse call graph tool exposed to workers
 ├── edit_file                — atomic find-replace + auto-lint + reindex
 └── read_file                — token-aware: full content or AST overview + anchors

Code Index (code_index.py)   — multi-language symbol index, SQLite-backed
 ├── CODE_INDEX singleton     — one instance shared by all tools and orchestrators
 ├── set_project(root)        — opens/creates .opalacoder/code_index.sqlite
 ├── build()                  — full incremental scan (skips unchanged files by mtime)
 ├── rebuild_file(path)       — called automatically by write_file and edit_file
 ├── search(query)            — exact → prefix → substring match across all languages
 ├── find_callers(name)       — reverse call graph: who calls this symbol?
 ├── symbols_in_file(rel)     — used by get_file_overview for any language
 └── project_snapshot()       — symbol-enriched file listing fed to oracle prompts

Skill search order:
  1. {project_path}/skills/   (project-local, highest priority)
  2. {repo_root}/skills/      (OpalaCoder built-in skills)
  3. ~/.opalacoder/skills/    (user global skills)
```

## Adding a New Orchestrator Strategy

1. Create a class that extends `BaseOrchestratorStrategy` and implements `async run()`.
2. Decorate it with `@register_orchestrator("my_strategy_name")` in `orchestrator.py`
   (or import it there so the decorator runs at startup).
3. Set `strategy: my_strategy_name` under `agents.orchestrator` in `agents.yaml`.

```python
# orchestrator.py
@register_orchestrator("my_strategy")
class MyOrchestratorStrategy(BaseOrchestratorStrategy):
    async def run(self, user_request: str, history: str, **kwargs) -> str:
        ...
```

```yaml
# agents.yaml
agents:
  orchestrator:
    strategy: my_strategy
```

## Key Decisions

| Decision | Reason |
|---|---|
| Project replaces session as primary abstraction | Stable context anchor; avoids unbounded session drift |
| Skills fixed at project creation | Prevents irrelevant skill injection; reduces prompt size for small models |
| Orchestrator registry (`register_orchestrator`) | Allows multiple strategies selectable via `agents.yaml`; fails loudly on unknown names |
| `strategy: workflow` in `agents.yaml` | WorkflowOrchestratorStrategy is the current default; externalizes strategy choice |
| Classifiers instantiated once in `REPLState` | Avoids creating a new `LLMAgentBlock` on every user turn |
| All tools use `_PROJECT_PATH` as `cwd` | Eliminates path ambiguity; agent does not need to reason about absolute paths |
| SQLite persistence | Lightweight, zero-dependency, suitable for local-first tooling |
| Code index in SQLite | Survives session restarts; incremental rebuild by mtime avoids re-parsing unchanged files |
| `project_snapshot()` replaces plain file listing | Oracle receives symbol names per file → plans tasks at function granularity |
| Structured `Task` schema with semantic validation | Forces the planner to externalize class names, IDs, and file contracts; workers share no memory so all context must be explicit in the task |
| `_validate_task()` in oracle reflection loop | Rejects incomplete plans before they reach workers; feedback is specific (which field, why) |
| Commands list in `Task` (not monolithic description) | Each atomic step runs as a separate `LLMAgentBlock` call; shorter prompts, tighter focus, easier lint-cycle recovery |
| `context_block` preamble injected into every worker prompt | Worker never needs to infer cross-file contracts; goal, related files, and context are always present |
| `_auto_lint()` called in both `edit_file` and `write_file` | Syntax errors surface as tool return values; worker reflection loop self-corrects without human intervention |
| `reasoning_effort: "none"` for workers and classifiers | Gemma4 on Ollama returns reasoning in a separate field when thinking is enabled, leaving `tool_calls` empty; disabling think mode ensures tool calls are populated |
| `max_iterations=None` for workers | Worker is bounded by `max_tool_calls` only; `max_iterations` was binding earlier and preventing multi-step tasks from completing |
| Plan confirmation via `structured.py:confirm_plan()` | Uses instructor+MD_JSON structured output; immune to formatting variations from small models |

## Workflow Orchestrator: Plan→Execute→Verify Loop

The `WorkflowOrchestratorStrategy` drives execution entirely in Python. The LLM acts as a JSON oracle — it never runs tools directly in the planning or verification phase.

```
while heartbeats < max_hb:
    1. PLAN   — _oracle(PlanOutput) decomposes request into structured Tasks
                 _validate_task() runs semantic checks; reflection on failure
    2. EXECUTE — for each task:
                   for each command in task.commands:
                     LLMAgentBlock(prompt=context_block + command)
                     worker calls read_file / edit_file / write_file / run_command
                     lint errors returned as tool output → self-correction loop
    3. VERIFY  — _oracle(VerifyOutput) reads actual file contents on disk
                   done=True → exit
                   done=False → corrections (structured Tasks) → back to EXECUTE
```

The oracle uses `response_format={"type":"json_object"}` — the only JSON mode Ollama reliably supports. Both structural (`json.JSONDecodeError`, Pydantic `ValidationError`) and semantic (`_validate_task`) failures inject specific error messages back into the conversation and retry up to `MAX_REFLECT_RETRIES` times.

## Skill Scopes

Skills carry a `scope` frontmatter field that controls where they are injected:

- `all` — injected into both the intent classifier and the orchestrator
- `orchestrator` — injected only into the planner/executor (behavioral instructions)
- `classifier` — injected only into the intent classifier

## Known Removed / Dead Code

- `DeterministicOrchestratorStrategy` — described in prior versions of this doc but never implemented. References removed.
- `SubplanSchema`, `DecompositionResult`, `decompose_to_subplans()` — belonged to the unimplemented deterministic path. Removed from `structured.py`.
- `make_confirmation_agent()` — duplicated the confirmation logic already handled by `confirm_plan()` in `structured.py`. Removed from `agents.py`.
- `AutonomousOrchestratorStrategy` — superseded by `WorkflowOrchestratorStrategy`. The workflow strategy replaces the MemGPT single-agent loop with a Python-driven Plan→Execute→Verify cycle that is more controllable and testable.
- `Task.description` (string) — replaced by the structured `Task` schema (goal + commands + related_files + context + depends_on). The monolithic string gave workers no guaranteed context about cross-file contracts.
