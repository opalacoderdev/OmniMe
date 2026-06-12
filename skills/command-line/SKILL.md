---
name: command-line
description: Executes command-line operations to read, create, insert text, remove files and directories securely inside the project workspace.
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

Consider using `run_python_script` to call `scripts/command_executor.py` **only for structural operations** (insert text at a line, remove files/dirs, create empty directories). The syntax uses subcommands:

```
run_python_script("<command_executor.py_path>", "--project-path <project_path> <subcommand> <args>")
```

**Argument Explanation:**
- `<command_executor.py_path>`: The absolute path to the `command_executor.py` script.
- `<project_path>`: The path to the project root (e.g., `.`).
- `<subcommand> <args>`: The specific action you want to take (e.g., `remove-file`, `create-dir`) followed by its arguments.

**Concrete Examples:**

1. Creating a new directory:
`run_python_script("/home/user/skills/command-line/scripts/command_executor.py", "--project-path . create-dir src/components")`

2. Removing a file:
`run_python_script("/home/user/skills/command-line/scripts/command_executor.py", "--project-path . remove-file temp_debug.log")`

3. Renaming a directory:
`run_python_script("/home/user/skills/command-line/scripts/command_executor.py", "--project-path . rename old_folder new_folder")`

### 1. Insert Text

```
run_python_script("<command_executor.py_path>", "--project-path <project_path> insert-text <relative_file_path> --content-file /tmp/_opala_content.txt [--line <line_number>]")
```

For multi-line content, write it first with `write_file` to a temp path, then use `--content-file`.

### 2. Remove File
```
run_python_script("<command_executor.py_path>", "--project-path <project_path> remove-file <relative_file_path>")
```

### 3. Create Directory
```
run_python_script("<command_executor.py_path>", "--project-path <project_path> create-dir <relative_directory_path>")
```

### 4. Remove Directory
```
run_python_script("<command_executor.py_path>", "--project-path <project_path> remove-dir <relative_directory_path>")
```

### 5. Rename / Move File or Directory
```
run_python_script("<command_executor.py_path>", "--project-path <project_path> rename <relative_origin_path> <relative_dest_path>")
```

### 6. Copy File or Directory
```
run_python_script("<command_executor.py_path>", "--project-path <project_path> cp <relative_origin_path> <relative_dest_path>")
```
