---
name: command-line
description: Executes command-line operations to create, insert text, remove files and directories securely inside the project workspace.
---

# Command Line Skill

This skill provides the sub-agent with python command-line commands to manipulate files and directories securely and restricted to the project directory.

## Available Commands

You must execute the script `scripts/command_executor.py` using the `run_command` tool.
The following commands and arguments are supported:

### 1. Create File
Creates a new file with optional content.
`python3 <command_executor.py_path> --project-path <project_path> create-file <relative_file_path> [--content "<content>"]`

### 2. Insert Text
Inserts text into an existing file (or appends to the end if line is not specified).
`python3 <command_executor.py_path> --project-path <project_path> insert-text <relative_file_path> --content "<content>" [--line <line_number>]`

### 3. Remove File
Removes an existing file. Only paths inside the project are allowed.
`python3 <command_executor.py_path> --project-path <project_path> remove-file <relative_file_path>`

### 4. Create Directory
Creates a new directory.
`python3 <command_executor.py_path> --project-path <project_path> create-dir <relative_directory_path>`

### 5. Remove Directory
Recursively removes an existing directory. Only paths inside the project are allowed.
`python3 <command_executor.py_path> --project-path <project_path> remove-dir <relative_directory_path>`
