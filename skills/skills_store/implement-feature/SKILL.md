---
name: implement-feature
description: Creates, adds, modifies, or fixes code in project files. Use when the user asks to implement a new feature or fix a bug.
model: alternative
---

# Implement Feature

This skill runs the complete **Plan → Execute → Verify** loop over the project files. The engine is a deterministic Python script.

## MANDATORY RULE

For **any** code creation, modification, or bugfix, you **MUST** run the `run_workflow.py` script by calling the `run_command` tool. **DO NOT** use `write_file`, `edit_file`, or `replace_lines` directly inside this skill — these shortcuts skip planning and verification, producing unreliable results. Your sole execution action must be to **run the script** and, at the end, call `send_message` with a summary of what the script reported.

## How to execute

Call `run_command` with **exactly** this format (use the ABSOLUTE path of the script and the ABSOLUTE path of the request file, both provided in your prompt):

```
python <ABSOLUTE-PATH>/run_workflow.py --request-file <REQUEST-FILE-PATH> --intent <newfeat|bugfix>
```

Important rules:
- **DO NOT** type the request text directly into the command. The request is already saved in the file indicated in your prompt (`--request-file`). This prevents shell parsing errors with parentheses and quotes.
- Use the `--intent` indicated in your prompt.
- Your working directory is the project directory, not the skill directory — always use absolute paths.

- `--intent newfeat` → create something new / add functionality.
- `--intent bugfix` → fix something that exists and is broken (activates the vector index to locate the issue).
- `--model <value>` (optional) is automatically passed by the runner based on the `model` field of this SKILL.md; you do not need to specify it manually.

The script manages planning (with user approval), execution by workers with auto-linting, and layered verification, printing the final summary to standard output. Report what the script output to the user.
