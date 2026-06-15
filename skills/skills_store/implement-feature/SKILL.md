---
name: implement-feature
description: Creates, adds, modifies, or fixes code in project files. Use when the user asks to implement a new feature or fix a bug.
model: worker
---

# Implement Feature

This skill runs the complete **Plan → Execute → Verify** loop over the project files. The engine is a deterministic Python script.

## Execution Recommendation

For code creation, modification, or bugfixes, it is highly recommended to run the `run_workflow.py` script by calling the `run_python_script` tool. Using `write_file`, `edit_file`, or `replace_lines` directly inside this skill may skip planning and verification, producing unreliable results. You may execute the script and, at the end, call `send_message` with a summary of what the script reported.

## How to execute

Consider using `run_python_script` with the absolute path of the script and the absolute path of the request file:

```
run_python_script("<ABSOLUTE-PATH>/run_workflow.py", "--request-file <REQUEST-FILE-PATH>")
```

**Argument Explanation:**
- `<ABSOLUTE-PATH>/run_workflow.py`: The absolute path to the `run_workflow.py` script for this skill. This path is provided dynamically in your prompt.
- `<REQUEST-FILE-PATH>`: The absolute path to a text file containing the user's detailed request. Also provided in your prompt.

**Concrete Examples:**

1. Implementing a new login feature based on a request file:
`run_python_script("/home/user/project/skills/implement-feature/scripts/run_workflow.py", "--request-file /tmp/request_123.txt")`

2. Fixing an existing bug reported in a request file:
`run_python_script("/home/user/project/skills/implement-feature/scripts/run_workflow.py", "--request-file /tmp/request_456.txt")`

3. Adding a new dark mode toggle feature:
`run_python_script("/opt/opalacoder/skills/implement-feature/scripts/run_workflow.py", "--request-file /var/tmp/dark_mode_req.txt")`

Important rules:
- **DO NOT** type the request text directly into the command. The request is already saved in the file indicated in your prompt (`--request-file`). This prevents shell parsing errors with parentheses and quotes.
- Your working directory is the project directory, not the skill directory — always use absolute paths.
- `--model <value>` (optional) is automatically passed by the runner based on the `model` field of this SKILL.md; you do not need to specify it manually.

The script manages planning (with user approval), execution by workers with auto-linting, and layered verification, printing the final summary to standard output. Report what the script output to the user.
