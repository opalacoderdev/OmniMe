# Skills & Plugin System

OpalaCoder uses **skills** to give the orchestrator language-specific knowledge, and **plugins** to give workers language-specific tools. Both are declared in `.md` skill files and loaded automatically when a project uses that skill.

---

## Overview

| Layer | What it is | Who uses it |
|-------|-----------|-------------|
| Skill content | Reference rules in `.md` body | Planner + Reviewer (injected into system prompts) |
| Skill tools (`tools:`) | Python functions declared in frontmatter | Worker agents (real callable tools) |

---

## Skill File Format

Skill files live in the `skills/` directory (project-level, package-level, or `~/.opalacoder/skills/`).

```markdown
tags: html, css, javascript, js, web, frontend
description: Use when the user requests a plain HTML/CSS/JavaScript project.
scope: orchestrator
tools:
  - html_css_js_tools.search_html_css_js_bugs
---
## HTML / CSS / JavaScript Developer Rules

... reference rules injected into the planner ...
```

### Frontmatter fields

| Field | Required | Description |
|-------|----------|-------------|
| `tags` | yes | Comma-separated keywords used by the semantic router |
| `description` | yes | One-line description shown to the skill selector |
| `scope` | no | `all` (default), `orchestrator`, or `classifier` |
| `tools` | no | List of `module.function` entries — one per line under a YAML list |

---

## Tools Field

Each entry under `tools:` has the form `module_name.function_name`.

- `module_name` — the Python module filename (without `.py`) to search for in plugin directories.
- `function_name` — the name of the function exported from that module.

The function must be decorated with `@as_tool` from `agenticblocks.core.function_block`.

### Example

```yaml
tools:
  - html_css_js_tools.search_html_css_js_bugs
  - my_project_tools.check_api_contracts
```

---

## Plugin Search Order

When loading a tool, OpalaCoder searches for `<module_name>.py` in the following directories, **in order of priority**:

1. `{project_path}/plugins/` — project-local plugins (highest priority)
2. `{cwd}/.opalacoder/plugins/` — workspace plugins
3. `~/.opalacoder/plugins/` — user-global plugins
4. `{opalacoder_package}/plugins/` — built-in plugins (lowest priority)

The first directory containing the module wins. This allows projects to override built-in tools with custom implementations.

---

## Writing a Plugin Tool

A plugin module is a plain Python file with one or more `@as_tool`-decorated functions.

### Minimal example

```python
# my_project/plugins/my_tools.py
from agenticblocks.core.function_block import as_tool

@as_tool(
    name="check_api_contracts",
    description=(
        "Validate that all API endpoints defined in routes.py match the "
        "contracts declared in api_spec.json. Returns a list of mismatches."
    ),
)
def check_api_contracts(path: str = ".") -> str:
    # path is relative to the project root
    ...
    return "No mismatches found."
```

### Function signature rules

- Parameters must have **type annotations** and **default values** — OpalaCoder builds a Pydantic input model from them.
- The return type must be `str` (or a Pydantic `BaseModel`).
- Use `path: str = "."` as the conventional first parameter for file/directory targeting.

### Accessing project context

The project root is available via `opalacoder.tools.get_project_path()`:

```python
from opalacoder.tools import get_project_path, AGENT_PROGRESS, _preview

@as_tool(name="my_tool", description="...")
def my_tool(path: str = ".") -> str:
    AGENT_PROGRESS.update("my_tool", f"path={_preview(path)}")
    root = get_project_path()
    resolved = path if os.path.isabs(path) else os.path.join(root, path)
    ...
```

> **Note**: `get_project_path()` is set at the start of each workflow run. It is safe to call from any plugin.

### Progress reporting

Call `AGENT_PROGRESS.update(tool_name, args_preview)` at the start of your function so the live panel shows your tool is running.

---

## Declaring Tools in a Skill

Add a `tools:` block to the skill's YAML frontmatter:

```markdown
tags: python, django, rest
description: Use for Django REST Framework projects.
scope: orchestrator
tools:
  - django_tools.check_migrations
  - django_tools.validate_serializers
---
## Django REST Framework Rules
...
```

Save the file to `skills/django_rest.md` in your project directory.

When a project has the `django_rest` skill active, workers will automatically have `check_migrations` and `validate_serializers` as callable tools, and the planner will be told to call them at the start of fix/refactor tasks.

---

## Built-in Plugins

OpalaCoder ships built-in plugins in `opalacoder/plugins/`:

| Module | Tool | Description |
|--------|------|-------------|
| `html_css_js_tools` | `search_html_css_js_bugs` | JS syntax check + regex patterns for common HTML/CSS/JS bugs |

These are used by the `html_css_js` skill automatically. Project-level plugins with the same module name take precedence.

---

## Overriding a Built-in Plugin

Create `{project_path}/plugins/html_css_js_tools.py` with a function named `search_html_css_js_bugs`. It will shadow the built-in.

```python
# myproject/plugins/html_css_js_tools.py
from agenticblocks.core.function_block import as_tool

@as_tool(name="search_html_css_js_bugs", description="Custom JS checker for this project.")
def search_html_css_js_bugs(path: str = ".") -> str:
    # project-specific checks
    return "All good."
```

---

## How Tools Flow Through the System

```
Skill file (html_css_js.md)
  └── tools: html_css_js_tools.search_html_css_js_bugs
        │
        ▼
  load_skill_tools(project_skills, project_path)
        │  searches plugin dirs in priority order
        │  loads module via importlib
        │  extracts function → FunctionBlock
        ▼
  get_workflow_tools(skill_tools=[...])
        │  merges with base tools
        │  deduplicates by tool name
        ▼
  LLMAgentBlock(tools=[...])   ← worker has the tool
        │
  _planner_system(skill_tool_names=[...])
        └── system prompt lists available skill tools
            planner writes "Call search_html_css_js_bugs on script.js" as first command
```

---

## Quick Reference

```
skills/my_skill.md          ← skill file with tools: frontmatter
{project}/plugins/          ← project-specific plugin modules (highest priority)
{cwd}/.opalacoder/plugins/  ← workspace plugins
~/.opalacoder/plugins/      ← user-global plugins
opalacoder/plugins/         ← built-in plugins (lowest priority)
```

Key functions in `opalacoder/skills.py`:

| Function | Purpose |
|----------|---------|
| `_parse_skill_file(path)` | Parse frontmatter including `tools:` list |
| `find_plugin_module(name, project_path)` | Locate a module file in plugin search dirs |
| `load_skill_tools(project_skills, project_path)` | Load all skill tool callables |
