---
name: html-css-js
description: Regras de boas práticas e detector de contratos para web vanilla (HTML/CSS/JavaScript puro). Use ao criar ou corrigir páginas/apps web sem framework, bundler ou npm.
---

# HTML / CSS / JavaScript (vanilla)

Aplique estas regras quando o usuário pedir explicitamente uma aplicação web
**vanilla** (sem React/Vue, sem bundler, sem npm). A saída são arquivos `.html`,
`.css` e `.js` que abrem direto no navegador.

## Estrutura de arquivos
Prefira um único `index.html`; para complexidade média, separe em `index.html` +
`style.css` + `script.js`.

## Regras de HTML
1. Sempre `<!DOCTYPE html>` e `<meta charset="UTF-8">`.
2. `<link rel="stylesheet" href="style.css">` no `<head>`.
3. `<script src="script.js" defer></script>` (o `defer` garante DOM pronto).
4. Todo elemento interativo com `id` único e claro.

## Regras de JavaScript
1. Sempre `defer` no `<script>` ou envolva em `DOMContentLoaded`.
2. Nunca `var`; use `const`/`let`.
3. Nunca chame `addEventListener` em elemento possivelmente `null` — verifique
   `getElementById` ou use `defer`.
4. Para cálculos com strings (ex. display de calculadora), use `parseFloat`/`parseInt`.

## Regras de CSS
1. Variáveis CSS (`--color-primary`) em `:root`.
2. `box-sizing: border-box` global.
3. Sem `float`; use flexbox/grid.
4. Botões com `:hover` e `:active`.

## Detecção de contratos (script)

Antes de propor uma correção em HTML/CSS/JS, rode o detector de bugs de contrato
com `run_command`, usando o caminho ABSOLUTO do script (indicado no seu prompt na
seção "Scripts available in this skill"):

```
python <CAMINHO-ABSOLUTO>/check_contracts.py --project-path <DIRETÓRIO-DO-PROJETO>
```

Ele reporta linhas `[CONTRACT ERROR]` / `[SYNTAX ERROR]` / `[WARNING]` / `[INFO]`.
Uma `[CONTRACT ERROR]` indicando incompatibilidade entre o HTML e o JS deve ser
corrigida **no arquivo apontado** (geralmente o HTML, na linha indicada) — não
invente correções fora do que o detector aponta.
