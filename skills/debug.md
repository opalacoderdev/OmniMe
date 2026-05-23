tags: bug, bugs, debug, debugar, erro, error, fix, corrigir, problema, issue, falha, crash, exception, lint, análise, analyze, checar, check, inspecionar, inspect, detectar, detect
description: Use when the user asks to find, detect, or fix bugs, errors, or issues in the code. Instructs the agent to call search_bugs before proposing any fix.
scope: orchestrator
---
## Debug — Bug Detection Protocol

When the user asks to find bugs, debug, or check for errors in the code, you MUST follow this protocol:

### Step 1: Run search_bugs

Before writing any fix or plan, call `search_bugs` to get a structured list of detected issues:

```
search_bugs(path=".", llm_check=True)
```

- Use `path="."` to scan the entire project, or a specific file/directory if the user specified one.
- Set `llm_check=False` if the user wants a fast scan (linters + AST only).
- The tool runs three layers: linters (pyflakes/mypy/pylint), AST pattern checks, and an LLM spot-check on recently modified files.

### Step 2: Report findings

Present the results clearly grouped by severity:
- **ERROR** — must be fixed before shipping
- **WARNING** — should be reviewed
- **INFO** — informational

For each bug, include: file, line, rule, and message.

### Step 3: Fix (if requested)

If the user asks to fix the bugs:
1. Address ERROR-severity bugs first.
2. Use `edit_file` for targeted fixes — never rewrite entire files unless necessary.
3. After each fix, call `search_bugs` again on the affected file to confirm the issue is resolved.
4. Call `send_message` with a summary of what was fixed.
