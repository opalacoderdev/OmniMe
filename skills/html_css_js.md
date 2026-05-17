tags: html, css, javascript, js, web, webpage, page, frontend, calculator, form, dom, vanilla
description: Use when the user requests a plain HTML/CSS/JavaScript project (no framework, no bundler).
scope: orchestrator
---
## HTML / CSS / JavaScript Developer Rules

WHEN the user explicitly requests a **vanilla** web application (No React, no Vue, no bundlers, no npm), apply these rules.
All output must be raw `.html`, `.css`, and `.js` files that open directly in a browser.

### File Structure
Prefer a single `index.html` unless explicitly told otherwise.
For medium complexity, split into:
```
<project_dir>/
  index.html
  style.css
  script.js
```

### HTML Rules
1. Always use `<!DOCTYPE html>` and `<meta charset="UTF-8">`.
2. Load `<link rel="stylesheet" href="style.css">` in `<head>`.
3. Load `<script src="script.js" defer></script>` at the end of `<head>` (using `defer` ensures the DOM is ready before the script runs — never use inline `<script>` at the top of the body).
4. Give every interactive element a clear, unique `id` (e.g. `id="display"`, `id="btn-plus"`).

### JavaScript Rules
1. **Always wrap code in `DOMContentLoaded`** OR use the `defer` attribute on the script tag (both are acceptable; `defer` is preferred).
   ```js
   // Option A: defer attribute on <script> — no wrapper needed
   document.getElementById('btn').addEventListener('click', handler);

   // Option B: if not using defer
   document.addEventListener('DOMContentLoaded', () => {
     document.getElementById('btn').addEventListener('click', handler);
   });
   ```
2. Never use `var`; use `const` and `let`.
3. Never call `addEventListener` on a potentially `null` element. Always verify that `getElementById` returns a non-null value before using it, or use `defer`.
4. Keep state in plain variables or a small object — no frameworks.
5. For calculations that involve strings (e.g. calculator display values), always parse with `parseFloat()` or `parseInt()` before arithmetic.

### CSS Rules
1. Use CSS custom properties (`--color-primary`) in `:root` for all repeated values.
2. Use `box-sizing: border-box` globally: `*, *::before, *::after { box-sizing: border-box; }`.
3. Avoid `float`; use `flexbox` or `grid` for layout.
4. Button states: always define `:hover` and `:active` styles.

### Common Bugs to Avoid
- `Cannot read properties of null (reading 'addEventListener')` → script is running before the DOM is ready. Fix: use `defer` on `<script>` tag.
- Calculator buttons not working → check that button `id` values in HTML exactly match what `querySelector`/`getElementById` selects in JS.
- `file:` URL security errors in `<iframe>` → never embed the same page in an iframe.
