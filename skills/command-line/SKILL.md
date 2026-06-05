---
name: command-line
description: Executes command-line operations to create, insert text, remove files and directories securely inside the project workspace.
---

# Command Line Skill

This skill provides the sub-agent with tools to manipulate files and directories securely, restricted to the project directory.

## IMPORTANT: Creating or writing files

**Use `write_file` directly to create or overwrite any file.** Do NOT use `command_executor.py` for writing file content — shell quoting breaks with multi-line, HTML, CSS, or JavaScript content.

```
write_file("<relative_or_absolute_path>", "<full file content>")
```

Examples:
```
write_file("tictactoe.html", "<!DOCTYPE html>...")
write_file("src/utils.js", "function foo() {...}")
```

## Available Commands via command_executor.py

Use `run_command` to call `scripts/command_executor.py` **only for structural operations** (insert text at a line, remove files/dirs, create empty directories). The syntax uses subcommands:

```
python3 <command_executor.py_path> --project-path <project_path> <subcommand> <args>
```

### 1. Insert Text

```
python3 <command_executor.py_path> --project-path <project_path> insert-text <relative_file_path> --content-file /tmp/_opala_content.txt [--line <line_number>]
```

For multi-line content, write it first with `write_file` to a temp path, then use `--content-file`.

### 2. Remove File
```
python3 <command_executor.py_path> --project-path <project_path> remove-file <relative_file_path>
```

### 3. Create Directory
```
python3 <command_executor.py_path> --project-path <project_path> create-dir <relative_directory_path>
```

### 4. Remove Directory
```
python3 <command_executor.py_path> --project-path <project_path> remove-dir <relative_directory_path>
```
