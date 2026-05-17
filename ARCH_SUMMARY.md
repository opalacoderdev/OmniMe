# ABCode — Architecture Summary

## Focus

ABCode is designed to work with **small language models** (e.g. Mistral-Nemo, Llama 3 8B via Ollama) as its primary target. Large models (Gemini, GPT-4, Claude) are supported as a fallback for complex tasks, but the core design prioritizes correctness and usability under constrained context windows and limited reasoning capacity.

## Core Idea: Project-Centric Context Management

The central abstraction is the **project**, not the session. Every interaction happens within a named project that has a fixed filesystem path. This design decision exists for one reason: **context management**.

Small models degrade quickly when context is large, mixed, or unbounded. By anchoring all activity to a project, ABCode can:

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
      ├── Intent classifier  — routes input to: plan | chat | question | greetings
      ├── run_pipeline()     — triggers orchestration for planning tasks
      │    ├── AutonomousOrchestratorStrategy   (capable models)
      │    │    ├── generate_panorama()         phase 1: high-level plan
      │    │    ├── refine_plan()               phase 2: user refinement loop
      │    │    └── MemGPT agent loop           autonomous execution with tools
      │    └── DeterministicOrchestratorStrategy (small models)
      │         ├── generate_panorama()         phase 1
      │         ├── refine_plan()               phase 2
      │         ├── decompose_plan()            phase 3: subplan decomposition
      │         ├── execute_subplans()          phase 4: WorkflowGraph execution
      │         └── aggregate_results()         phase 5: final summary
      └── chat_agent         — MemGPT agent for Q&A and conversation

Project (project.py)
 ├── ProjectData             — name, path, skills, description, history, plan state
 └── ProjectStore            — SQLite CRUD for projects and message history

Skills (skills.py)
 ├── load_project_skills()   — loads only skills listed in the project
 ├── select_skills_for_project() — LLM picks skills from description at creation
 ├── find_skill_file()       — resolves <name>.md across skill search dirs
 └── get_relevant_skills_llm()  — semantic router (uses project skills only)

Tools (tools.py)              — file read/write, run_command, search_code, ask_human
 └── PROJECT_PATH global     — all tools resolve paths relative to the project dir

Skill search order:
  1. {project_path}/skills/   (project-local, highest priority)
  2. {repo_root}/skills/      (ABCode built-in skills)
  3. ~/.abcode/skills/        (user global skills)
```

## Key Decisions

| Decision | Reason |
|---|---|
| Project replaces session as primary abstraction | Stable context anchor; avoids unbounded session drift |
| Skills fixed at project creation | Prevents irrelevant skill injection; reduces prompt size for small models |
| `/addskill` command | Lets users extend skills without restarting or recreating the project |
| `abcode` skill always loaded | Core behavioral instructions must always be present |
| Two orchestrator strategies | Small models cannot reliably drive autonomous tool loops; deterministic DAG is more reliable for them |
| All tools use `PROJECT_PATH` as `cwd` | Eliminates path ambiguity; agent does not need to reason about absolute paths |
| SQLite persistence | Lightweight, zero-dependency, suitable for local-first tooling |

## Skill Scopes

Skills carry a `scope` frontmatter field that controls where they are injected:

- `all` — injected into both the intent classifier and the orchestrator
- `orchestrator` — injected only into the planner/executor (behavioral instructions)
- `classifier` — injected only into the intent classifier
