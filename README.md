# OpalaCoder

**OpalaCoder** is an autonomous coding agent with interactive planning, modular execution, and persistent project memory. It is designed to work well with small and less autonomous models while maintaining the feel of a fully autonomous agent. It is built using the **AgenticBlocks.IO** framework.

---

## Features

### Project-Centric Context Management
OpalaCoder centers around **projects** rather than transient chat sessions. Every interaction happens within a named project with a fixed filesystem path. This anchors the LLM context, loads only project-relevant skills, scopes all file and terminal operations, and persists history effectively for both small local models and large hosted APIs.

### Advanced Semantic Router (Chain of Thought)
Uses an LLM for semantic routing with internal reasoning (Chain of Thought). It translates user demands to English internally, correctly deduces the intent, and seamlessly routes execution even for multilingual commands, injecting only the necessary context from specific **Skills** (`skills/*.md`).

### Dynamic Model Selection (Double Inference Architecture)
OpalaCoder dynamically evaluates task complexity. For trivial tasks, it uses a fast default model (e.g., `ollama/mistral-nemo`). If the task requires architectural refactoring or advanced complex logic, it automatically falls back to a more powerful alternative model configured via API keys.

### Interactive Planning
The agent receives a natural language demand, generates a high-level landscape plan, and enters a refinement loop with the user until the plan is approved. The approved plan is then automatically decomposed into executable sub-steps (subplans).

### Execution with Retry & Strategy Routing
OpalaCoder delegates orchestration to specialized strategies. Small models use a deterministic execution pipeline (DAG), while capable models can use a fully autonomous agent loop. If a sub-step fails, the agent retries (up to a configurable limit) by injecting the previous error into the context for self-correction.

### Execution Modes

| Mode   | Behavior |
|--------|---------------|
| `plan` | Generates a plan and asks for user approval before executing (default) |
| `auto` | Executes everything without interruptions — ideal for automated pipelines |
| `edit` | Requests user confirmation only for sensitive operations (file creation/deletion, network calls, etc.) |

### Persistent Projects and CLI Commands
Each execution belongs to a named project with continuous memory. During the chat with OpalaCoder, you can interact with the state manager using native commands:
- `/help` or `/h`: Shows available commands.
- `/clear`: Clears the memory and history of the current project.
- `/rename <new_name>`: Renames the active project.
- `/list`: Lists all projects saved in SQLite.
- `/load <name>` and `/delete <name>`: Loads or deletes old projects. (Deleting also asks to delete the project directory).
- `/skills`: Lists available skills and highlights the active ones for the project.
- `/addskill <name>` and `/rmskill <name>`: Adds or removes specific skills for the current project.
- `/undo`: Reverts the last change made by the agent via internal shadow VCS.
- `/commit <msg>`: Forces a commit to the local shadow git control.
- `/exit` or `/quit`: Exits the application.

### Shadow Git (VCS)
Every project comes with an isolated "Shadow Git" (`.opalacoder/.git`) that automatically checkpoints the codebase before and after execution. This allows for safe iteration without muddying the user's main git repository, and enables the `/undo` command.

### Elegant Terminal
Formatted output with [Rich](https://github.com/Texel-io/rich): banners, progress spinners, plan panels, per-subplan status tables, and highlighted error reports.

### Modular Architecture
The code is divided into independent, easy-to-debug modules:

```text
opalacoder/
├── config.py       Global settings (model, retries, mode, db, VCS)
├── terminal.py     Rich output (banners, spinners, panels, tables)
├── project.py      SQLite project management and state
├── vcs.py          Internal shadow Git strategies (auto, hybrid, agent-driven)
├── agents.py       LLM agent factories
├── planner.py      Pipeline: panorama → refinement → decomposition
├── orchestrator.py Strategy-based execution (deterministic vs autonomous)
└── cli.py          Argparse + project bootstrap + REPL
```

---

## Requirements

- Python 3.11+
- [agenticblocks](https://github.com/gilzamir/agenticblocks) installed in the virtual environment
- [Rich](https://github.com/Texel-io/rich): `pip install rich`
- An accessible LLM server (e.g., [Ollama](https://ollama.com) with `mistral-nemo`, or any model supported by [litellm](https://docs.litellm.ai))

---

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd OpalaCoder

# Create and activate the virtual environment
python -m venv .env
source .env/bin/activate          # Linux/macOS
# .env\Scripts\activate           # Windows

# Install the dependencies
pip install -r requirements.txt
```

### Environment Variables (Optional)

Create a `.env` file in the project root to override defaults:

```env
# Default LLM model (any litellm supported string)
OPALA_MODEL=ollama/mistral-nemo
```

---

## How to Run

```bash
# Activate the virtual environment
source .env/bin/activate

# Default execution (plan mode)
python main.py

# Choose execution mode
python main.py --mode auto
python main.py --mode plan
python main.py --mode edit

# Use another model
python main.py --model ollama/llama3

# Custom database path
python main.py --db /path/to/projects.db

# Show version
python main.py --version

# Help
python main.py --help
```

---

## Project Flow

```text
1. Banner + Mode Selection
       ↓
2. Project Configuration
   ├── New Project   → Name, Path, Description -> LLM selects skills
   └── Existing      → Load context and skills
       ↓
3. User enters demand
       ↓
4. Agent generates landscape (high-level plan)
       ↓
5. Refinement loop (plan/edit modes)
   ├── User approves → proceeds
   └── User suggests changes → agent refines and loops back to step 5
       ↓
6. Decomposition into subplans (SP-1, SP-2, …)
       ↓
7. Sequential execution by dependency
   └── For each subplan:
       ├── Pre-run VCS checkpoint
       ├── Executes generated code (AgenticBlocks WorkflowGraph)
       ├── Success → Next subplan
       └── Failure → Retry up to max_retries, then report error
       ├── Post-run VCS checkpoint
       ↓
8. Aggregation: Final synthesized result of the operation
       ↓
9. Result displayed + project saved
```

---

## Advanced Configuration

### Build & Test Commands
Run tests in the `tests` directory after implementing a new feature:

```bash
python -m pytest
```

### Change the Default Model

Edit `opalacoder/config.py`:

```python
DEFAULT_MODEL = "ollama/mistral-nemo"  # change here
```

Or use the environment variable `OPALA_MODEL`.

### Sensitive Operations

In `opalacoder/config.py`:

```python
SENSITIVE_OPS = {
    "write_file", "delete_file", "run_shell",
    "send_network_request", "create_user", "delete_user",
    # add keywords here for operations that require confirmation in edit mode
}
```

---

## Security

- The `edit` mode requires explicit confirmation for operations affecting the filesystem, network, or user accounts.
- Generated code is executed locally. For greater isolation, the `CodePlanExecutorBlock` from the AgenticBlocks library supports execution in a Docker container — edit `make_executor_block` in `opalacoder/agents.py` changing `execution_mode="local"` to `execution_mode="docker"`.
- Never run the agent in `auto` mode with access to production systems without reviewing the generated subplans.

---

## License

MIT
