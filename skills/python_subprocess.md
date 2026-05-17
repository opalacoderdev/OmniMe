tags: python, shell, bash, subprocess, script, command
description: Anti-hang protections for shell commands (subprocess) in Python scripts (devnull).
scope: orchestrator
---
Whenever you need to run shell commands from Python:
Use `import subprocess` and call the function passing `stdin=subprocess.DEVNULL`:
`subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)`

The `stdin=subprocess.DEVNULL` flag is MANDATORY. It prevents infinite hangs if any command tries to be interactive (asking for Y/N, passwords, or menu choices). The script must be 100% automated.

Print the `stdout` and `stderr` of each command so we can log and validate the execution result.
