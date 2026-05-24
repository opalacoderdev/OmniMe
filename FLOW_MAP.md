# OpalaCoder — Mapa do Fluxo de Execução

> Arquivo gerado para auditoria. Referências de linha apontam para o estado atual do código.

---

## Visão geral (entrada → saída)

```
User request
     │
     ▼
[WorkflowOrchestrator.run()]           workflow_orchestrator.py:697
     │
     ├─ Setup: VCS checkpoint, code index, skill tools/reviewers
     │
     ▼
[_orchestration_loop()]                workflow_orchestrator.py:1157
     │
     ├─ PRÉ-PLANNING: skill tool pre-scan  ← NOVO
     │
     ▼
[Planner Oracle]  →  PlanOutput         workflow_orchestrator.py:1245
     │
     └─ loop: para cada task pendente
           │
           ├─ VCS checkpoint (rollback point)
           ├─ errors_before = _run_skill_scan()  ← NOVO
           │
           ▼
       [Worker]  →  worker_result        workflow_orchestrator.py:1301
           │
           ▼
       [_review_task()]                  workflow_orchestrator.py:945
           │
           ├─ CHECK 1: lint
           ├─ CHECK 2: arquivos mudaram no disco?
           ├─ CHECK 3: partial edit (old_str not found)?
           ├─ CHECK 4: H2 before/after (orchestrator)  ← NOVO
           ├─ CHECK 5: skill reviewers (plugins)        ← NOVO
           └─ CHECK 6: LLM reviewer oracle
                │
                ├─ done=True  → task.status = "done"
                └─ done=False → task.failure_count++
                                └─ se >= MAX_TASK_FAILURES → abort
                                └─ senão → adiciona correction task ao plano e retenta
```

---

## Fase 0 — Setup (run, linhas 697–795)

| Passo | O que faz | Onde |
|---|---|---|
| VCS auto-checkpoint | Salva estado do projeto em `.opalacoder/.git` antes de qualquer mudança | ~758 |
| Code index build | Indexa arquivos do projeto para buscas do worker | ~764 |
| Carregar skill tools | `load_skill_tools()` lê frontmatter `tools:` de cada skill ativa e importa as funções | ~773 |
| Carregar skill reviewers | `load_skill_reviewers()` lê frontmatter `reviewer:` e importa as funções | ~774 |
| Montar planner_sys | `_planner_system()` — sistema de prompt do planner LLM | ~787 |

**Skill ativa por padrão para projetos HTML/JS/CSS:** `html_css_js`
- Tool registrada: `html_css_js_tools.search_html_css_js_bugs`
- Reviewer registrado: `html_css_js_tools.html_css_js_reviewer`

---

## Fase 1 — Pré-planning (linhas 1195–1243)

### 1a. File snippets
Extrai conteúdo de arquivos mencionados explicitamente na request do usuário (ex: "corrige o `index.html`").

### 1b. Skill tool pre-scan ← **PONTO CRÍTICO**
```
para cada st em _skill_tools:
    chama st._func(".")          ← sync, direto na função, não via wrapper async
    filtra linhas com [CONTRACT ERROR] / [SYNTAX ERROR] / [ERROR]
    injeta no planning_prompt como "Skill tool pre-scan"
```
**Por que importa:** sem isso, o planner só vê o sintoma ("botão 9 não funciona") e chuta o arquivo errado (script.js). Com o pre-scan ele vê `[CONTRACT ERROR] index.html:42: botão 9 tem data-value="multiply"` e cria a task no arquivo correto.

**Só linhas de erro bloqueantes são injetadas** — WARNING/INFO causariam tasks desnecessárias.

### 1c. planning_prompt montado
```
Project files: <snapshot do diretório>
Relevant file contents and diagnostics:
  <file snippets>
  Skill tool pre-scan:
    [search_html_css_js_bugs]
    [CONTRACT ERROR] index.html:42: ...
Conversation history: ...
User request: ...
```

### 1d. Planner oracle
`_oracle(PlanOutput, planner_sys, planning_prompt)` → retorna lista de `Task` com:
- `id`, `goal`, `commands[]`, `related_files[]`, `depends_on[]`

O system prompt do planner (`_planner_system`, linha 370) contém instrução crítica:
> "CRITICAL — when the planning prompt contains a skill tool pre-scan with [CONTRACT ERROR]: create tasks ONLY for the files explicitly named in 'FIX REQUIRED IN <file>'. Do NOT create tasks for files the scan does not flag."

---

## Fase 2 — Loop de execução de tasks (linhas 1263–1380)

Para cada task pendente (respeitando `depends_on`):

### 2a. VCS checkpoint por task (linha 1292)
`_vcs.manual_commit("pre-task t1: ...")` — permite rollback se a task falhar.

### 2b. errors_before = _run_skill_scan() (linha 1299) ← **NOVO**
Captura o conjunto de erros bloqueantes **antes** do worker rodar.
```python
def _run_skill_scan() -> set[str]:       # linha 920
    # chama cada st._func(".") de _skill_tools
    # retorna set de linhas [CONTRACT ERROR]/[SYNTAX ERROR]/[ERROR]
```
Este snapshot será comparado com o estado **depois** do worker para detectar se o erro foi de fato corrigido.

### 2c. Worker (linha 1301)
`_run_worker_safe(task)` → `_run_worker(task, ...)` (linha 540)

O worker é um `LLMAgentBlock` com ferramentas:
- `read_file`, `edit_file`, `create_file`, `list_dir`, `search_code`
- + skill tools do projeto (ex: `search_html_css_js_bugs`)

O worker recebe o `task.goal` + `task.commands[]` como prompt e executa.
Ao final, o footer do resultado anota `[Tools invoked: edit_file, read_file, ...]`.

---

## Fase 3 — Review (`_review_task`, linhas 945–1143)

Os checks são executados **em ordem**. O primeiro que reprovar devolve `VerifyOutput(done=False)` sem executar os seguintes.

### CHECK 1 — Lint (linha 948)
`_run_lint(task)` verifica sintaxe JS (node --check) / Python (py_compile).
- Erro de sintaxe → **rejeição automática**, sem chamar LLM.

### CHECK 2 — Arquivos mudaram? (linha 969)
`_git_changed_files()` usa `git status --porcelain` no shadow git.
- Worker chamou ferramenta de escrita **mas nenhum arquivo mudou** → **rejeição automática**.
- Worker não chamou nenhuma ferramenta de escrita e nenhum arquivo mudou → **rejeição automática**.

### CHECK 3 — Partial edit (linha 1034)
Contabiliza `old_str not found` no worker_result. Se > 0, injeta nota no contexto do LLM reviewer (não rejeita automaticamente, mas avisa).

### CHECK 4 — H2 before/after orchestrator (linha 1051) ← **NOVO**
```python
errors_after = _run_skill_scan()
unresolved = errors_before & errors_after   # erros que existiam antes e ainda existem
new_errors  = errors_after - errors_before  # erros novos introduzidos pelo worker

if unresolved or new_errors:
    → rejeição automática, passa as linhas de erro como corrections
```
**Por que é genérico:** compara sets de strings — não sabe nada sobre o tipo de erro. Funciona para qualquer ferramenta registrada em `tools:` que emita linhas `[CONTRACT ERROR]` / `[SYNTAX ERROR]` / `[ERROR]`.

### CHECK 5 — Skill reviewers (linha 1080) ← **NOVO**
Para cada função em `_skill_reviewers`:
```python
if "errors_before" in sig.parameters:
    resultado = reviewer(project_path, task_goal, related_files, errors_before=errors_before)
else:
    resultado = reviewer(project_path, task_goal, related_files)

if resultado["done"] == False:
    → rejeição, corrections = resultado["corrections"]
```
O `html_css_js_reviewer` aceita `errors_before` e faz a mesma lógica de before/after, mas com acesso direto ao scanner (pode gerar mensagens mais detalhadas que o CHECK 4).

### CHECK 6 — LLM reviewer oracle (linha 1100)
Só chega aqui se todos os checks anteriores passaram.
Manda para o LLM:
- task JSON, lint summary, arquivos que mudaram, worker_result, conteúdo atual dos `related_files`

Retorna `VerifyOutput(done, summary, corrections[])`.

---

## O que acontece quando review.done=False

```
task.failure_count += 1

if failure_count >= MAX_TASK_FAILURES:
    → abort com mensagem de erro para o usuário

else:
    para cada Task em review.corrections:
        adiciona ao plan.tasks com id único
    → próxima iteração do while loop pega a correction task como pending
```

---

## Arquivos relevantes

| Arquivo | Responsabilidade |
|---|---|
| [opalacoder/workflow_orchestrator.py](opalacoder/workflow_orchestrator.py) | Fluxo completo: planner, worker, reviewer |
| [opalacoder/plugins/html_css_js_tools.py](opalacoder/plugins/html_css_js_tools.py) | Scanner de bugs HTML/JS (`search_html_css_js_bugs`) e reviewer (`html_css_js_reviewer`) |
| [opalacoder/skills.py](opalacoder/skills.py) | Carregamento de skills, tools e reviewers por frontmatter |
| [skills/html_css_js.md](skills/html_css_js.md) | Frontmatter: `tools:` e `reviewer:` que ativam o scanner e o reviewer |

---

## O que verificar manualmente para o bug do micalc

1. **O planner viu o erro certo?**
   Rode: `python tests/test_planner_output.py micalc "botão 9 não funciona"`
   Procure no output: `Skill tool pre-scan` com `[CONTRACT ERROR]` apontando para `index.html`.
   Se não aparecer: o scanner `search_html_css_js_bugs` não detectou o bug.

2. **O scanner detecta o bug?**
   ```bash
   cd /caminho/do/micalc
   python -c "
   import sys; sys.path.insert(0, '/home/gilzamir/projetos/OpalaCoder')
   from opalacoder.plugins.html_css_js_tools import search_html_css_js_bugs
   print(search_html_css_js_bugs('.'))
   "
   ```
   Deve aparecer `[CONTRACT ERROR]` para o botão 9.

3. **O H2 rejeita corretamente?**
   Se o worker mudar o arquivo errado (script.js em vez de index.html), o `errors_before` ainda vai conter o CONTRACT ERROR do botão 9. O `_run_skill_scan()` após o worker vai retornar o mesmo erro. `unresolved = errors_before & errors_after` vai ser não-vazio → rejeição automática no CHECK 4.

4. **O reviewer do plugin foi chamado?**
   Procure no log do agente por `[skill_reviewer]` ou `[H2-REJECT]`.
