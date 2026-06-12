---
name: html-css-js
description: Best practice rules and contract detector for vanilla web (pure HTML/CSS/JavaScript). Use when creating or fixing web pages/apps without frameworks, bundlers, or npm.
---

# HTML / CSS / JavaScript (vanilla)

Apply these rules when the user explicitly requests a **vanilla** web application (no React/Vue, no bundler, no npm). The outputs are `.html`, `.css`, and `.js` files that open directly in the browser.

## File Structure
Prefer a single `index.html`; for medium complexity, separate into `index.html` + `style.css` + `script.js`.

## HTML Rules
1. Always `<!DOCTYPE html>` and `<meta charset="UTF-8">`.
2. `<link rel="stylesheet" href="style.css">` inside `<head>`.
3. `<script src="script.js" defer></script>` (using `defer` ensures the DOM is ready).
4. Every interactive element must have a unique and clear `id`.

## JavaScript Rules
1. Always use `defer` in `<script>` or wrap logic in `DOMContentLoaded`.
2. Never use `var`; use `const`/`let`.
3. Never call `addEventListener` on a possibly `null` element — verify with `getElementById` or use `defer`.
4. For string calculations (e.g., calculator display), use `parseFloat`/`parseInt`.

## CSS Rules
1. CSS variables (`--color-primary`) in `:root`.
2. `box-sizing: border-box` globally.
3. No `float`; use flexbox/grid.
4. Buttons with `:hover` and `:active`.

## Contract Detection (script)

Before proposing any fix in HTML/CSS/JS, you may run the contract bug detector with `run_python_script`, using the ABSOLUTE path of the script (indicated in your prompt in the "Scripts available in this skill" section):

```
run_python_script("<ABSOLUTE-PATH>/check_contracts.py", "--project-path <PROJECT-DIRECTORY>")
```

**Argument Explanation:**
- `<ABSOLUTE-PATH>/check_contracts.py`: The absolute path to the `check_contracts.py` script for this skill. This path is provided dynamically in your prompt.
- `<PROJECT-DIRECTORY>`: The absolute path to the web project directory containing your HTML, CSS, and JS files.

**Concrete Examples:**

1. Checking contracts in the current directory:
`run_python_script("/home/user/project/skills/html-css-js/scripts/check_contracts.py", "--project-path .")`

2. Checking a specific web subfolder:
`run_python_script("/home/user/project/skills/html-css-js/scripts/check_contracts.py", "--project-path /home/user/project/frontend_app")`

3. Checking a project located elsewhere:
`run_python_script("/opt/opalacoder/skills/html-css-js/scripts/check_contracts.py", "--project-path /var/www/html/my-site")`

It reports `[CONTRACT ERROR]` / `[SYNTAX ERROR]` / `[WARNING]` / `[INFO]` lines.
A `[CONTRACT ERROR]` indicating an incompatibility between the HTML and the JS must be fixed **in the pointed file** (usually the HTML, at the indicated line) — do not invent fixes outside what the detector points out.
