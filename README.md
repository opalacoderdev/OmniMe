# OpalaCoder

**OpalaCoder** is an autonomous coding agent built on the **[AgenticBlocks.IO](https://github.com/gilzamir/agenticblocks)** framework. It features a project-centric context model and a modular, skills-oriented architecture optimized to run efficiently with local LLMs.

---

## Core Architecture & Features

### 1. Project-Centric Context
All operations happen within a named project mapped to a fixed directory. This grounds the agent's workspace, scopes file/terminal access, maintains SQLite-based project memory, and keeps LLM context windows small and focused.

### 2. MemGPT Chat Orchestrator
The main entry point is a persistent **MemGPT Chat Orchestrator** (`MemGPTAgentBlock`). Rather than running a static intent classifier, the orchestrator converses with the user, manages long-term memory, and dynamically routes complex tasks by invoking active skills via tool-calling (`run_skill`).

### 3. Skills-Oriented Design (Anthropic Standard)
Capabilities are defined as modular **skills** (defined via `SKILL.md` declarations and optional Level 3 python/bash scripts).
- **Opt-in Activation**: Projects declare active skills in a local `skills.yaml` file.
- **Ephemeral Sub-Agents**: When a skill is invoked, the orchestrator spawns a focused sub-agent (`LLMAgentBlock`) dedicated to executing that skill's workflow.
- **Dialogue Interceptor**: The sub-agent communicates directly with the user, and an interceptor synchronizes the exchange back to the orchestrator's memory.

### 4. Code Generation (`implement-feature` Skill)
Software development and bug-fixing tasks are handled by the default `implement-feature` skill, running a structured Plan → Execute → Verify loop:
- **Interactive Planning**: Generates high-level task plans and refines them based on user feedback.
- **Shadow Git Checkout**: Automatically checkpoints code to an isolated repository (`.opalacoder/.git`) before plan execution, allowing instant rollback via `/undo`.
- **Auto-Linting**: Validates changes using syntax checkers (`node --check`, `py_compile`) after each file edit, letting the worker self-correct syntax errors autonomously.

### 5. Web-Based IDE GUI (Cross-Platform)
OpalaCoder features an integrated desktop GUI built using React, Vite, and `pywebview`:
- **Cross-Platform Support**: Works seamlessly on Linux and Windows. If `pywebview` is not available, it automatically falls back to hosting a local web server and launching the interface in your default browser.
- **Integrated Terminal**: Includes a real-time xterm.js terminal with shell/PTY integration for running and inspecting commands natively.
- **Git Source Control Sidebar**: A dedicated panel that tracks file modifications (color-coded as Modified/Untracked/Deleted) and provides a commit interface.
- **Global Settings Panel**: Customize the editor font size, tab size, and word wrapping, with dynamic toggle support for Light and Dark themes.
- **About Tab**: Version tracking (currently `0.1.25 alfa`), licensing, and developer details in the settings panel.

### 6. Persistent Projects and CLI Commands

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

### 7. Modular Architecture

```text
opalacoder/
├── cli.py                  Entrypoint, project loading, REPL loop
├── memgpt_runtime.py       MemGPT chat orchestrator and run_skill tool integration
├── agents.py               Agent creation helper functions
├── config.py               Global settings loader and CLI parser
├── skills.py               Skill loading, selection, and routing
├── project.py              SQLite project management and state
├── vcs.py                  Shadow git strategies (auto, hybrid, agent-driven, none)
├── ide_server.py           Asynchronous HTTP and REST server hosting the IDE GUI
├── agent_stdin.py          JSON stdin/stdout protocol server for remote control
├── code_index.py           Multi-language symbol index (SQLite-backed, incremental)
├── vector_index.py         Vector index of chunks for semantic code lookup
└── tools.py                Shared tool definitions (run_command, memory APIs)
```

---

## Requirements

### 1. Core & CLI Requirements
- **Python 3.11+**
- **[agenticblocks](https://github.com/gilzamir/agenticblocks)** (install from source)
- **Local SQLite support** (standard in python)
- **Local LLM Engine (Recommended: Ollama 0.24.0+)** with models available:
  - **Default & Alternative models**: `ministral-3:14b` (or `gemma4:latest`, `mistral-nemo:latest`)
  - Any model supported by [litellm](https://docs.litellm.ai) works.

> [!TIP]
> **Hardware Acceleration & GPU Drivers:**
> To run large models (like `gemma4` or `ministral-3:14b`) efficiently on local backends (such as Ollama), it is highly recommended to use GPU hardware acceleration.
> - **NVIDIA GPUs**: Ensure you have official **NVIDIA Drivers** and the **CUDA Toolkit** installed so that Ollama can offload model layers to GPU VRAM.
> - **AMD & Apple Silicon**: Ollama also supports ROCm (AMD) and Metal (Apple Silicon) natively. Make sure your local setup is utilizing GPU acceleration to avoid slow CPU execution times.

### 2. Web IDE / GUI Requirements
- **Desktop Window Mode (Optional)**: Launches a native app window using `pywebview`.
  - **Windows**: Works out of the box using Windows Webview2 (Edge).
  - **Linux**: Requires **WebKit2GTK** python bindings (specifically `python3-gi` and `gir1.2-webkit2-4.1`) or **Qt5/Qt6** (PyQt/PySide) installed on the system.
  - **Browser Fallback**: If desktop window dependencies are missing, OpalaCoder automatically starts the IDE server and opens it in your default web browser (`http://127.0.0.1:3000`).
- **Frontend Development (Optional)**: If you intend to compile the React/Vite frontend source code under `gui_src/`, you will need **Node.js 18+** and **npm**. (Compiled assets are already bundled in default packages).

---

## Installation

Try:

```bash
pip install opalacoder
```

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

OpalaCoder supports three main execution modes:

### 1. Web-Based IDE GUI (Default)
Launches the integrated React desktop application. It opens as a local app window (via `pywebview`) or falls back to your web browser:
```bash
source .env/bin/activate
python main.py                        # Launches GUI by default
# or explicitly:
python main.py --gui
```

### 2. Interactive CLI REPL
Starts the standard CLI terminal planner/execution loop:
```bash
source .env/bin/activate
python main.py --cli                  # Activates CLI REPL mode
python main.py --cli --mode auto      # run without interruptions
python main.py --cli --mode edit      # confirm sensitive operations
python main.py --cli --model ollama/gemma4  # override model
python main.py --db /path/to/db       # custom database path
python main.py --version
python main.py --help
```

### 3. Stdin/Stdout JSON Protocol Server
Launches the agent in background headless mode, communicating via single-line JSON messages:
```bash
source .env/bin/activate
python main.py --stdin
```

---

## Compiling Frontend GUI (Optional)

If you are developing or making changes to the React GUI, you can recompile the assets:
```bash
cd gui_src
npm install
npm run build
```
This builds the SPA bundle and saves it directly into the Python package distribution at `opalacoder/gui/`.

## Project Flow

```text
main() or `--gui` (server mode)
  │
  ├── startup_menu() ───────── Load/Create project, discover skills (via skills.yaml)
  │
  └── repl_loop() ──────────── Instantiate MemGPT chat-orchestrator
        │
        ├── User enters command (e.g. `/help`, `/undo`) ── Dispatched to CLI commands
        │
        └── User enters demand ────────────────────────── MemGPT.run(user_input)
              │
              ├── Direct chat (greetings, project status, general questions)
              │
              └── Request matches active skill ───────────── run_skill(name, context)
                    │
                    ├── Instantiate ephemeral sub-agent (LLMAgentBlock)
                    ├── Sub-agent loads SKILL.md and Level 3 scripts (e.g. implement-feature)
                    ├── Sub-agent executes with tools, talks to user (dialogue interceptor)
                    └── Return result to MemGPT orchestrator
```

---

## Configuration (`agents.yaml`)

The main configuration file. Key fields and role overrides:

```yaml
default: ollama/ministral-3:14b      # default model for all agents
alternative: ollama/ministral-3:14b  # model for complex tasks

llm_defaults:
  temperature: 1.0
  max_tokens: 8128
  num_ctx: 8192

agents:
  # The fixed chat-orchestrator of the skills-oriented architecture.
  memgpt:
    temperature: 1.0
    num_ctx: 16384
    max_heartbeats: 20

  # drives the plan→execute→review loop inside the implement-feature skill
  orchestrator:
    temperature: 1.0
    num_ctx: 16384
    max_heartbeats: 20
    strategy: workflow

  # executes each task command with code editing tools
  worker:
    temperature: 1.0
    max_tokens: 8128
    num_ctx: 16384
    reasoning_effort: "none"  # Must stay "none" for tool-calling integration
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
