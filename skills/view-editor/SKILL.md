---
name: view-editor
description: Allows inspecting the current file opened in the editor, as well as the active text selection or full content.
---

# View Editor Skill

This skill allows you to inspect what file is currently open in the IDE editor, the full code content of the file, and any text highlighted/selected by the user.

## Usage

You must execute the script `scripts/run_view_editor.py` inside the `view-editor` skill directory.

Run the following command using the `run_command` tool:
`python3 <run_view_editor.py_path> --project-path <project_path>`

It will automatically locate the staged editor state inside the project folder at `.opalacoder/_editor_state.json` and output the path, current selection, and full content in markdown.
