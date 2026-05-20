# OpalaCoder — Architecture Summary

## Focus

OpalaCoder is designed to work with **small language models** (e.g. Ministral-3 14B, Gemma 4 via Ollama) as its primary target. The core design prioritizes correctness and usability under constrained context windows and limited reasoning capacity. Larger models are supported as an alternative for complex tasks via the `alternative` key in `agents.yaml`.

## Core Idea: Project-Centric Context Management

The central abstraction is the **project**, not the session. Every interaction happens within a named project that has a fixed filesystem path. This design exists for one reason: **context management**.

Small models degrade quickly when context is large, mixed, or unbounded. By anchoring all activity to a project, OpalaCoder can:

- Inject a stable, minimal project header (`[PROJECT: name | PATH: /path]`) into every prompt instead of growing conversation state
- Load only the skills relevant to that project type (selected at creation, not dynamically per-request)
- Scope all file reads, writes, and commands to the project directory, eliminating ambiguity
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
 │    │                    (field_validator coerces dict/list → JSON string for
 │    │                    models that generate object-typed context)
 │    └── depends_on     — explicit ordering between tasks
 ├── _validate_task()     — semantic guardrail: rejects empty goal/commands/context
 │                          and CSS/JS tasks without related_files
 ├── _oracle()            — litellm call with JSON mode + structural + semantic reflection
 │                          DEBUG prints raw content/reasoning per attempt to stderr
 ├── _run_worker()        — iterates task.commands; each command = one LLMAgentBlock call
 │                          with context_block preamble (TASK GOAL / RELATED FILES /
 │                          CONTEXT / COMMAND) injected into every worker prompt
 │                          Worker uses termination_tools=["send_message"] so the loop
 │                          stops immediately when send_message is called
 └── _planner_system()    — system prompt with full Task schema + field rules + examples
                            includes hard rule: redeclaration fix = delete the line,
                            never change const→let

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
 │                             `line` param resolves ambiguous old_str by proximity
 │                             new_str="" deletes the matched line
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

VCS (vcs.py)                 — shadow git strategies
 ├── _run_shadow_git(cmd, project_path)  — always receives explicit project_path;
 │                                         never uses get_project_path() global
 ├── AutoGitStrategy          — setup() + manual_commit() before execution (default)
 ├── HybridGitStrategy        — same + exposes git tools to workers
 ├── AgentDrivenGitStrategy   — workers have full git control
 └── NoGitStrategy            — VCS disabled
 Auto-checkpoint flow:
   set_project_context() called first → get_project_path() correct →
   _vcs.setup() → _vcs.manual_commit("auto-checkpoint before plan execution") →
   /undo calls undo_last() → reset --hard HEAD~1 on shadow git

Skill search order:
  1. {project_path}/skills/   (project-local, highest priority)
  2. {repo_root}/skills/      (OpalaCoder built-in skills)
  3. ~/.opalacoder/skills/    (user global skills)

Benchmark (scripts/)
 ├── collect_jsbench.py   — collects JS bug-fix instances from GitHub
 │                          uses timeline API (not search) to find linked PRs
 │                          filters: has jest/vitest, pure .js files, ≤3 files changed
 └── eval_jsbench.py      — evaluates OpalaCoder on collected instances
                            clone at base_commit → npm test (before) →
                            run OpalaCoder → npm test (after) → pass/fail
```

## Adding a New Orchestrator Strategy

1. Create a class that extends `BaseOrchestratorStrategy` and implements `async run()`.
2. Decorate it with `@register_orchestrator("my_strategy_name")`.
3. Set `strategy: my_strategy_name` under `agents.orchestrator` in `agents.yaml`.

```python
@register_orchestrator("my_strategy")
class MyOrchestratorStrategy(BaseOrchestratorStrategy):
    async def run(self, user_request: str, history: str, **kwargs) -> str:
        ...
```

## Key Decisions

| Decision | Reason |
|---|---|
| Project replaces session as primary abstraction | Stable context anchor; avoids unbounded session drift |
| Skills fixed at project creation | Prevents irrelevant skill injection; reduces prompt size for small models |
| Orchestrator registry (`register_orchestrator`) | Allows multiple strategies selectable via `agents.yaml`; fails loudly on unknown names |
| `strategy: workflow` in `agents.yaml` | WorkflowOrchestratorStrategy is the current default |
| Classifiers instantiated once in `REPLState` | Avoids creating a new `LLMAgentBlock` on every user turn |
| All tools use `_PROJECT_PATH` as `cwd` | Eliminates path ambiguity; agent does not need to reason about absolute paths |
| SQLite persistence | Lightweight, zero-dependency, suitable for local-first tooling |
| Code index in SQLite | Survives session restarts; incremental rebuild by mtime avoids re-parsing unchanged files |
| `project_snapshot()` replaces plain file listing | Oracle receives symbol names per file → plans tasks at function granularity |
| Structured `Task` schema with semantic validation | Forces the planner to externalize class names, IDs, and file contracts |
| `_validate_task()` in oracle reflection loop | Rejects incomplete plans before they reach workers |
| Commands list in `Task` (not monolithic description) | Each atomic step runs as a separate `LLMAgentBlock` call; shorter prompts, tighter focus |
| `context_block` preamble injected into every worker prompt | Worker never needs to infer cross-file contracts |
| `_auto_lint()` called in both `edit_file` and `write_file` | Syntax errors surface as tool return values; worker self-corrects |
| `reasoning_effort: "none"` for workers and classifiers | Gemma4/Ministral on Ollama leave `tool_calls` empty when thinking is enabled |
| `max_iterations=None` for workers | Worker bounded by `max_tool_calls` only |
| `termination_tools=["send_message"]` in LLMAgentBlock | Worker loop stops immediately when send_message is called; requires agenticblocks ≥ commit 98795f3 |
| `field_validator` on `Task.context` | Coerces dict/list → JSON string for models (e.g. Mistral) that generate object-typed context |
| `edit_file` `line` param | Resolves ambiguous old_str by picking occurrence closest to given line number |
| `set_project_context()` before VCS checkpoint | Ensures `get_project_path()` returns the correct user project path, not OpalaCoder's own root |
| Intent classifier prompt in English only | LLM generalizes to PT-BR from English examples; PT-BR examples in LLM prompts cause confusion |
| `ministral-3:14b` as default model | Better instruction-following than mistral-nemo for structured JSON; faster than gemma4 |

## Workflow Orchestrator: Plan→Execute→Verify Loop

```
while heartbeats < max_hb:
    1. PLAN   — _oracle(PlanOutput) decomposes request into structured Tasks
                 _validate_task() runs semantic checks; reflection on failure
    2. EXECUTE — for each task:
                   for each command in task.commands:
                     LLMAgentBlock(prompt=context_block + command,
                                   termination_tools=["send_message"])
                     worker calls read_file / edit_file / write_file / run_command
                     lint errors returned as tool output → self-correction loop
                     loop exits immediately on send_message call
    3. VERIFY  — _oracle(VerifyOutput) reads actual file contents on disk
                   done=True → exit
                   done=False → corrections (structured Tasks) → back to EXECUTE
```

## Skill Scopes

Skills carry a `scope` frontmatter field:

- `all` — injected into both the intent classifier and the orchestrator
- `orchestrator` — injected only into the planner/executor
- `classifier` — injected only into the intent classifier

## Known Removed / Dead Code

- `AutonomousOrchestratorStrategy`, `autonomous_orchestrator.py` — superseded by `WorkflowOrchestratorStrategy`
- `profile_executor.py`, `profiles.py`, `profiles/` — profile-based execution replaced by skill system
- `make_confirmation_agent()` — duplicated logic already in `confirm_plan()` in `structured.py`
- `DeterministicOrchestratorStrategy` — described in prior versions but never implemented
- `SubplanSchema`, `DecompositionResult`, `decompose_to_subplans()` — belonged to unimplemented deterministic path
- `Task.description` (string) — replaced by structured `Task` schema (goal + commands + related_files + context + depends_on)
