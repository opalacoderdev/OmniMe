# OpalaCoder IDE

**OpalaCoder IDE** is a streamlined, local-first AI coding editor and testbed optimized for open-source LLMs. Built on the **[AgenticBlocks.IO](https://github.com/gilzamir/agenticblocks)** framework, it features a project-centric context model and a modular, skills-oriented architecture designed to run efficiently with local LLMs. 

Rather than serving as a full replacement for primary production setups, OpalaCoder provides a lightweight, developer-focused interface to test, run, and develop with local LLMs (such as `gemma4:12b` or `gpt-oss:20b`) and cloud models (such as `gemma4:31b-cloud` via Ollama).

---

## Core Architecture & Features

### 1. Project-Centric Context
All operations happen within a named project mapped to a fixed directory. This grounds the agent's workspace, scopes file/terminal access, maintains SQLite-based project memory, and keeps LLM context windows small and focused.

### 2. MemGPT Chat Orchestrator
The main entry point is a persistent **MemGPT Chat Orchestrator** (`MemGPTAgentBlock`). Rather than running a static intent classifier, the orchestrator converses with the user, manages long-term memory, and dynamically routes complex tasks by invoking active skills via tool-calling (`run_skill`).

### 3. Skills-Oriented Design
Capabilities are defined as modular **skills** (defined via `SKILL.md` declarations and optional Level 3 python/bash scripts).
- **Opt-in Activation**: Projects declare active skills in a local `skills.yaml` file.
- **Ephemeral Sub-Agents**: When a skill is invoked, the orchestrator spawns a focused sub-agent (`LLMAgentBlock`) dedicated to executing that skill's workflow.
- **Dialogue Interceptor**: The sub-agent communicates directly with the user, and an interceptor synchronizes the exchange back to the orchestrator's memory.

### 4. Code Generation (`implement-feature` Skill)
Software development and bug-fixing tasks are handled by the default `implement-feature` skill, running a structured Plan → Execute → Verify loop:
- **Interactive Planning**: Generates high-level task plans and refines them based on user feedback.
- **Shadow Git Checkout**: Automatically checkpoints code to an isolated repository (`.opalacoder/.git`) before plan execution, allowing instant rollback via `/undo`.
- **Auto-Linting**: Validates changes using syntax checkers (`node --check`, `py_compile`) after each file edit, letting the worker self-correct syntax errors autonomously.

### 5. Web-Based IDE GUI
OpalaCoder features an integrated desktop GUI built using React, Vite, and `pywebview`:
- **Cross-Platform Support**: Works seamlessly on Linux and Windows. If `pywebview` is not available, it automatically falls back to hosting a local web server and launching the interface in your default browser.
- **Integrated Terminal**: Includes a real-time xterm.js terminal with shell/PTY integration for running and inspecting commands natively.
- **Git Source Control Sidebar**: A dedicated panel that tracks file modifications (color-coded as Modified/Untracked/Deleted) and provides a commit interface.
- **Global Settings Panel**: Customize the editor font size, tab size, and word wrapping, with dynamic toggle support for Light and Dark themes.

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
  - **Default local model**: `gemma4:12b`
  - **Alternative local model**: `gpt-oss:20b`
  - Any model supported by [litellm](https://docs.litellm.ai) works.

> [!TIP]
> **Hardware Acceleration & GPU Drivers:**
> To run large models (like `gemma4:12b` or `gpt-oss:20b`) efficiently on local backends (such as Ollama), it is highly recommended to use GPU hardware acceleration. Ensure you have official GPU drivers and the appropriate CUDA/ROCm/Metal environment configured.

### 2. Web IDE / GUI Requirements
- **Desktop Window Mode (Optional)**: Launches a native app window using `pywebview`.
  - **Windows**: Works out of the box using Windows Webview2 (Edge).
  - **Linux**: Requires **WebKit2GTK** python bindings (specifically `python3-gi` and `gir1.2-webkit2-4.1`) or **Qt5/Qt6** (PyQt/PySide) installed on the system.
  - **Browser Fallback**: If desktop window dependencies are missing, OpalaCoder automatically starts the IDE server and opens it in your default web browser (`http://127.0.0.1:3000`).
- **Frontend Development (Optional)**: If you intend to compile the React/Vite frontend source code under `gui_src/`, you will need **Node.js 18+** and **npm**. (Compiled assets are already bundled in default packages).

---

## Installation

You can install it directly via pip:

```bash
pip install opalacoder
```

Or build and run it from source:

```bash
git clone https://github.com/opalacoderdev/OpalaCoder
cd OpalaCoder

python -m venv .env
source .env/bin/activate          # Linux/macOS
# .env\Scripts\activate           # Windows

# Install agenticblocks from source
pip install -e /path/to/agenticblocks

# Install OpalaCoder dependencies
pip install -r requirements.txt
```

---

## How to Run

OpalaCoder supports three main execution modes:

### 1. Web-Based IDE GUI (Default)
Launches the integrated React desktop application. It opens as a local app window (via `pywebview`) or falls back to your web browser:
```bash
source .env/bin/activate
python main.py
```

### 2. Interactive CLI REPL
Starts the standard CLI terminal planner/execution loop:
```bash
source .env/bin/activate
python main.py --cli
```

### 3. Stdin/Stdout JSON Protocol Server
Launches the agent in background headless mode, communicating via single-line JSON messages:
```bash
source .env/bin/activate
python main.py --stdin
```

---

## Configuration (`agents.yaml`)

Configure model mappings and agent parameters inside `~/.opalacoder/agents.yaml`:

```yaml
default: ollama/gemma4:12b      # default local model
alternative: gemini/gemini-3.1-flash-lite  # fallback model for complex tasks

llm_defaults:
  temperature: 0.7
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
    temperature: 0.7
    num_ctx: 16384
    reasoning_effort: "none"  # Must stay "none" for tool-calling integration
```

---

## Build & Test

```bash
python -m pytest tests/ -q
```

---

## License & Feedback

OpalaCoder IDE is open source and available under the **MIT** license.

*   **Repository**: [https://github.com/opalacoderdev/OpalaCoder](https://github.com/opalacoderdev/OpalaCoder)
