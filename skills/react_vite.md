tags: react, vite, npm, npx, node, javascript, js, ts, frontend
description: Use ONLY if the user asks to initialize, create, or configure a React or Vite project.
scope: orchestrator
---
If you need to initialize a Vite project using `npx create-vite`, you MUST use the 100% automated command passing the flags `-y` and `--template react` (or another template if explicitly requested).
Example: `npx -y create-vite@latest <project_name> --template react`
