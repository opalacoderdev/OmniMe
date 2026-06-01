# OpalaCoder

**OpalaCoder** is an autonomous coding agent with interactive planning, modular execution, and persistent project memory. It is designed to work well with small local models while maintaining the feel of a fully autonomous agent. Built on the **[AgenticBlocks.IO](https://github.com/gilzamir/agenticblocks)** framework.

---

## Features

### Project-Centric Context Management
OpalaCoder centers around **projects** rather than transient chat sessions. Every interaction happens within a named project with a fixed filesystem path. This anchors the LLM context, loads only project-relevant skills, scopes all file and terminal operations, and persists history — keeping prompts small and focused even for constrained local models.

### Plan → Execute → Verify Loop
The agent generates a structured plan (decomposed into typed `Task` objects), executes each task command with a focused `LLMAgentBlock` worker, and verifies the result against actual file contents. If verification fails, corrective tasks are injected and the loop continues.

### Interactive Planning
After generating a high-level plan, OpalaCoder enters a refinement loop with the user. The approved plan is then automatically decomposed into atomic executable steps. Each worker receives a self-contained context block (goal, related files, operational context, command) so it never needs to infer cross-file contracts.

### Auto-lint Self-Correction
`edit_file` and `write_file` run `node --check` (JS/TS) or `py_compile` (Python) after every write. Syntax errors are returned as tool output so the worker can self-correct within the same execution loop — no human intervention needed.

### Shadow Git (`/undo`)
Every project has an isolated shadow git (`.opalacoder/.git`) that checkpoints the codebase automatically before plan execution. `/undo` restores the previous state without touching the user's main git repository.

### Semantic Intent Router
Uses an LLM classifier to route user messages to the correct handler: `plan`, `question`, `chat`, `greetings`, `resume`, or `command_hint`. Correctly handles multilingual input and status/history questions without misclassifying them as development tasks.

### Dynamic Model Selection
Evaluates task complexity and automatically uses the `alternative` model (configurable in `agents.yaml`) for tasks that require deeper reasoning.

### Web-Based IDE GUI (Cross-Platform)
OpalaCoder features an integrated desktop GUI built using React, Vite, and `pywebview`:
- **Cross-Platform Support**: Works seamlessly on Linux and Windows. If `pywebview` is not available, it automatically falls back to hosting a local web server and launching the interface in your default browser.
- **Integrated Terminal**: Includes a real-time xterm.js terminal with shell/PTY integration for running and inspecting commands natively.
- **Git Source Control Sidebar**: A dedicated panel that tracks file modifications (color-coded as Modified/Untracked/Deleted) and provides a commit interface.
- **Global Settings Panel**: Customize the editor font size, tab size, and word wrapping, with dynamic toggle support for Light and Dark themes.
- **About Tab**: Version tracking (currently `0.1.4 alfa`), licensing, and developer details in the settings panel.

### Persistent Projects and CLI Commands

| Command | Description |
|---|---|
| `/help` | Show available commands |
| `/clear` | Clear memory and history of the current project |
| `/rename <name>` | Rename the active project |
| `/list` | List all saved projects |
| `/load <name>` | Load an existing project |
| `/delete <name>` | Delete a project (optionally deletes its directory) |
| `/skills` | List available skills and active ones for the project |
| `/addskill <name>` / `/rmskill <name>` | Add or remove skills |
| `/undo` | Revert the last agent change via shadow VCS |
| `/commit <msg>` | Manually commit to the shadow git |
| `/exit` / `/quit` | Exit the application |

### Modular Architecture

```text
opalacoder/
├── config.py              Global settings (model, retries, git strategy)
├── terminal.py            Rich output (banners, spinners, panels, tables)
├── project.py             SQLite project management and state
├── vcs.py                 Shadow git strategies (auto, hybrid, agent-driven, none)
├── agents.py              LLM agent factories
├── planner.py             Panorama → refinement → plan decomposition
├── orchestrator.py        Strategy registry and base class
├── workflow_orchestrator.py  WorkflowOrchestratorStrategy (default)
├── workflow_tools.py      Worker tools: edit_file, read_file, find_symbol, send_message
├── tools.py               Base tools: write_file, run_command, search_code
├── code_index.py          Multi-language symbol index (SQLite-backed, incremental)
├── skills.py              Skill loading, selection, and routing
├── embeddings.py          Sentence-transformer embeddings for intent fallback
└── cli.py                 Argparse + project bootstrap + REPL
```

---

## Requirements

- Python 3.11+
- [agenticblocks](https://github.com/gilzamir/agenticblocks) (install from source)
- An Ollama instance with the default model available:
  - **Default model**: `ministral-3:14b`
  - **Alternative model** (complex tasks): also `ministral-3:14b` by default; change in `agents.yaml`
  - Other tested models: `gemma4:latest`, `mistral-nemo:latest`
  - Any model supported by [litellm](https://docs.litellm.ai) works
- **Recommended Ollama version**: `0.24.0+`

---

## Installation

```bash
git clone https://github.com/gilzamir/OpalaCoder
cd OpalaCoder

python -m venv .env
source .env/bin/activate          # Linux/macOS
# .env\Scripts\activate           # Windows

# Install agenticblocks from source first
pip install -e /path/to/agenticblocks

# Install OpalaCoder dependencies
pip install -r requirements.txt
```

### Environment Variables (Optional)

```env
# Override default model (any litellm-supported string)
OPALA_MODEL=ollama/ministral-3:14b
```

---

## How to Run

```bash
source .env/bin/activate

python main.py                        # default (plan mode)
python main.py --mode auto            # no interruptions
python main.py --mode edit            # confirm sensitive operations
python main.py --model ollama/gemma4  # override model
python main.py --db /path/to/db       # custom database path
python main.py --version
python main.py --help
```

---

## Project Flow

```
1. Banner + Mode Selection
2. Project Configuration
   ├── New  → Name, Path, Description → LLM selects skills
   └── Load → restore context and skills
3. User enters demand
4. Intent classification (plan / question / chat / ...)
5. [plan] Generate panorama (high-level plan)
6. Refinement loop — user approves or requests changes
7. Plan decomposed into Tasks
8. Pre-execution VCS checkpoint (shadow git)
9. For each Task → for each command:
   ├── LLMAgentBlock worker executes with tools
   ├── edit_file / write_file → auto-lint → self-correction
   └── send_message terminates worker immediately
10. Verification oracle reads files on disk
    ├── done=True  → finish
    └── done=False → inject correction tasks → back to step 9
11. Result displayed + project saved
```

---

## Configuration (`agents.yaml`)

The main configuration file. Key fields:

```yaml
default: ollama/ministral-3:14b      # default model for all agents
alternative: ollama/ministral-3:14b  # model for complex tasks
git_strategy: auto                   # auto | hybrid | agent_driven | none

agents:
  orchestrator:
    num_ctx: 16384
    max_heartbeats: 20   # max tasks in the plan
    strategy: workflow
  worker:
    num_ctx: 16384
    reasoning_effort: "none"  # must stay "none" for tool_calls to be populated
```

Full per-agent overrides for `temperature`, `max_tokens`, `num_ctx`, `reasoning_effort`, and `debug` are supported for every agent role.

---

## Benchmark

A JS bug-fix benchmark is included in `scripts/`:

```bash
# Collect instances from GitHub (requires gh CLI authenticated)
python scripts/collect_jsbench.py --limit 50 --out datasets/jsbench

# Evaluate OpalaCoder on collected instances
python scripts/eval_jsbench.py --limit 10
```

Results are written to `datasets/jsbench_results.json` with per-instance pass/fail and a summary fix rate.

---

## Build & Test

```bash
python -m pytest tests/ -q
```

---

## License

MIT
