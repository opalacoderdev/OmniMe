# 05 — VCS Sombra (Git Sombra)

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). Este subsistema é **reusado integralmente** — a
> única mudança é de quem o aciona: onde se lê "o orquestrador", no desenho-alvo é
> o **script Level 3 da skill `implement-feature`** (ver [03](03-skill-implement-feature.md)).

Cada projeto tem um repositório git **sombra** isolado, separado do git principal
do usuário, que faz checkpoints automáticos do código. Isso habilita `/undo` sem
tocar no histórico de versionamento do usuário. Fonte:
[vcs.py](../../opalacoder/vcs.py).

---

## 1. Repositório sombra

O git sombra vive em `<projeto>/.opalacoder/.git`, com a árvore de trabalho
apontando para a raiz do projeto. Todos os comandos usam essa indireção
([vcs.py:51](../../opalacoder/vcs.py#L51)):

```
git --git-dir=<projeto>/.opalacoder/.git --work-tree=<projeto> <comando>
```

`_init_shadow_git` ([vcs.py:65](../../opalacoder/vcs.py#L65)) inicializa o repo se
ausente, configura um `core.excludesFile` que ignora `.env`, `node_modules/`,
`__pycache__/`, `.venv/`, e faz o commit inicial (`Initial checkpoint (Auto)`).

> Por usar `--git-dir`/`--work-tree` explícitos, o git sombra **não** interfere
> com um `.git` normal que o usuário tenha no mesmo diretório.

---

## 2. Estratégias

`get_vcs_strategy(name, project_path)` ([vcs.py:240](../../opalacoder/vcs.py#L240))
seleciona uma das implementações de `VersionControlStrategy`. A estratégia ativa
vem de `git_strategy` em `config.yaml` (ver [07-configuracao.md](07-configuracao.md));
se o nome for desconhecido, cai em `hybrid`.

| Estratégia | `setup` | `pre_run`/`post_run` (checkpoints automáticos) | Ferramentas git para o agente |
|---|---|---|---|
| `auto` | inicializa sombra | sim | **nenhuma** (modo determinístico) |
| `hybrid` | inicializa sombra | sim | `git_status`, `git_diff`, `git_commit` |
| `agent_driven` | inicializa sombra | não | `git_status`, `git_diff`, `git_commit` |
| `none` | nada | não | nenhuma; `manual_commit`/`undo_last` retornam "VCS is disabled." |

Todas as estratégias com sombra implementam `manual_commit(message)` e
`undo_last()` de forma idêntica.

> O orquestrador de workflow gerencia seus próprios checkpoints diretamente via
> `manual_commit` (ver §3), independentemente dos hooks `pre_run`/`post_run` da
> estratégia.

---

## 3. Fluxo de checkpoint no orquestrador

Em [workflow_orchestrator.py](../../opalacoder/workflow_orchestrator.py):

1. **Checkpoint pré-execução** ([:843](../../opalacoder/workflow_orchestrator.py#L843)),
   após `set_project_context()` para que `get_project_path()` esteja correto:
   ```
   _vcs = get_vcs_strategy(get_git_strategy(), get_project_path())
   _vcs.setup()
   _vcs.manual_commit("auto-checkpoint before plan execution")
   ```
2. **Checkpoint por tarefa** ([:1424](../../opalacoder/workflow_orchestrator.py#L1424)),
   antes de cada tarefa rodar: `manual_commit("pre-task <id>: <goal>")`. Isso
   permite reverter ao estado pré-tarefa se a revisão exigir reexecução —
   evitando que um retry tente um `edit_file old_str` sobre um arquivo já
   modificado pela primeira tentativa.
3. **Rollback em falha de oráculo** ([:1456](../../opalacoder/workflow_orchestrator.py#L1456)):
   se o oráculo revisor falha de formato e ainda há tentativas, o orquestrador faz
   `undo_last()` para reexecutar a tarefa a partir de um estado limpo.

`_git_changed_files()` usa `git status --porcelain` no sombra para detectar tanto
modificados (`M`) quanto novos não rastreados (`??`) — `git diff HEAD` perderia
arquivos recém-criados.

---

## 4. `/undo` e `/commit`

Expostos como comandos do REPL (ver [cli_commands.py](../../opalacoder/cli_commands.py)):

- **`/undo`** → `undo_last()`:
  ```
  git reset --hard HEAD~1
  git clean -fd
  ```
  Requer ao menos 2 commits no sombra (inicial + pré-execução). Se só o commit
  inicial existe, `rev-parse HEAD~1` falha e retorna
  `"Cannot undo. No previous checkpoints."`
- **`/commit <msg>`** → `manual_commit(msg)`: faz `add .` e commit no sombra.
