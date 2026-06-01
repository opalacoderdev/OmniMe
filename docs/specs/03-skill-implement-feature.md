# 03 — Skill `implement-feature`

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). A skill `implement-feature` **reusa** o loop
> Planejar→Executar→Verificar existente
> ([workflow_orchestrator.py](../../opalacoder/workflow_orchestrator.py)) como seu
> **script Level 3 executado via bash** — o loop permanece determinístico em
> Python. Marcadores **⚠ a aprovar** indicam decisões pendentes.

A skill que cria, altera e corrige código é a peça que carrega o motor mais
pesado do OpalaCoder. Ela existe porque modelos locais pequenos **não conduzem de
forma confiável** um loop de planejamento/execução/verificação de ~1500 linhas —
por isso esse loop fica em Python, e a SKILL.md apenas instrui *quando e como*
invocá-lo.

---

## 1. Estrutura da skill

```text
skills/implement-feature/
├── SKILL.md                 # Level 1 + 2: quando usar e como chamar o script
└── scripts/
    └── run_workflow.py      # Level 3: o loop plan/execute/verify (código atual)
```

`SKILL.md` (resumo):

```yaml
---
name: implement-feature
description: Cria, adiciona, altera ou corrige código em arquivos do projeto.
  Use quando o usuário pede implementação ou correção de funcionalidade.
---
# Implement Feature
## Instructions
Execute o loop completo via run_command, com caminhos ABSOLUTOS:
`python <abs>/run_workflow.py --request-file <abs> --intent <newfeat|bugfix>`
O script conduz planejamento, execução e verificação e imprime o resultado.
```

O **sub-agente** instanciado por `run_skill` lê esta `SKILL.md` (já no seu system
prompt) e chama `run_command` para rodar o script — o código do loop **nunca entra
no contexto** (só a saída do script). O pedido viaja por `--request-file` (não na
linha de comando) para evitar erros de shell com parênteses/aspas — ver
[06 §3](06-skills-e-plugins.md#3-invocação-a-tool-run_skill).

---

## 2. O motor (loop reusado)

O script Level 3 encapsula o que hoje é `WorkflowOrchestratorStrategy.run`. A
mecânica permanece a descrita abaixo; o **único reposicionamento** é que ela passa
a ser disparada por bash a partir da skill, não por `run_pipeline`.

> **Modelo dos papéis internos.** O loop usa os modelos dos papéis
> `orchestrator`/`worker` de `agents.yaml`
> ([workflow_orchestrator.py:387](../../opalacoder/workflow_orchestrator.py#L387)).
> Como esta skill é script-driven, o runner **repassa** o campo `model` da
> `SKILL.md` ao script — `run_workflow.py --model <valor>` — que o aplica como
> default desses papéis. Ver
> [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai).

```
run_workflow(request, intent)
  ├─ set_project_context()        ← define get_project_path()
  ├─ _plan_and_refine()           ← panorama + aprovação do usuário (planner.py)
  ├─ VCS auto-checkpoint          ← git sombra antes de tocar arquivos (ver 05)
  ├─ CODE_INDEX.build()           ← índice incremental de símbolos
  │
  └─ loop:
       ├─ FASE 1 — PLAN    (oracle JSON → PlanOutput, com reflexão)
       ├─ FASE 2 — EXECUTE (workers LLMAgentBlock com tools + auto-lint)
       └─ FASE 3 — VERIFY  (oracle JSON → VerifyOutput, lê arquivos em disco)
```

### Schema de `Task`

Inalterado em relação ao código atual
([workflow_orchestrator.py:59](../../opalacoder/workflow_orchestrator.py#L59)):
`id`, `goal`, `commands`, `related_files`, `context`, `depends_on`,
`review_only`, `status`, `failure_count`, `oracle_failure_count`.

### Oráculo com reflexão

Inalterado: `_oracle()` faz chamada JSON
(`response_format={"type":"json_object"}`), valida contra Pydantic, e tenta
novamente injetando o erro. Orçamentos `MAX_REFLECT_RETRIES = 3` (formato) e
`MAX_SEMANTIC_RETRIES = 3` (validação semântica de `PlanOutput`) permanecem
separados.

### Validação semântica, bloco de contexto, escalonamento, revisão

Todos inalterados — ver o detalhamento já existente no código:
- `_validate_task` ([workflow_orchestrator.py:101](../../opalacoder/workflow_orchestrator.py#L101)).
- Bloco de contexto do worker e `termination_tools=["send_message"]`
  ([workflow_orchestrator.py:686](../../opalacoder/workflow_orchestrator.py#L686)).
- Escalonamento para `ALTERNATIVE_MODEL` em falha
  ([workflow_orchestrator.py:758](../../opalacoder/workflow_orchestrator.py#L758)).
- Revisão em camadas (lint autoritativo → houve escrita → comparação H2 →
  revisores de plugin → oráculo LLM)
  ([workflow_orchestrator.py:1041](../../opalacoder/workflow_orchestrator.py#L1041)).
- Loop de execução com checkpoint por tarefa, `MAX_TASK_FAILURES = 3`,
  `MAX_REVIEWER_ORACLE_FAILS = 2`
  ([workflow_orchestrator.py:1397](../../opalacoder/workflow_orchestrator.py#L1397)).

---

## 3. `intent` (newfeat vs bugfix)

O parâmetro `--intent` seleciona o prompt de planejamento e o pré-processamento,
como hoje:

- `newfeat` → `_planner_system` + snapshot de símbolos + trechos de arquivos
  mencionados.
- `bugfix` → `_planner_system_bugfix` + pré-scan de skills (linhas bloqueantes) +
  **contexto vetorial** (top-K chunks via índice vetorial; ver
  [04-memoria.md](04-memoria.md#4-índice-vetorial-vector_indexpy)).

`intent` é um **parâmetro único** desta skill (decisão confirmada — não há skill
`fix-bug` separada). Ver [06 §7](06-skills-e-plugins.md#7-skills-embutidas-previstas).

---

## 4. Relação com a fala ao usuário

O loop interage com o usuário na fase de refinamento de plano (`_plan_and_refine`).

**Decisão de implementação:** o refinamento de plano é **não-interativo por padrão**
quando rodado como script (`run_workflow.py` auto-aprova o panorama). Isso evita
travar num `T.ask` sem terminal e mantém o sub-agente simples; o usuário continua
conversando com o MemGPT depois. A flag `--interactive` reativa o refinamento via
terminal quando desejado. O orquestrador recebeu um parâmetro `interactive`
(default `True`, preservando o caminho legado quando chamado diretamente).

---

## 5. Retomada e checkpoints

**Implementado:** ao detectar uma execução não finalizada (campos de plano salvos
ou checkpoint do git sombra), o REPL roteia a retomada **pelo MemGPT** — chama
`state.memgpt.run(...)` com uma instrução de "continuar a implementação anterior",
e o MemGPT então decide chamar `run_skill("implement-feature", ...)`. Não há mais
`run_pipeline`. Ver [02 §4](02-memgpt-orquestrador.md#4-retomada-de-execução-resume).

Os checkpoints do git sombra (pré-execução e por tarefa) permanecem como descrito
em [05-vcs-sombra.md](05-vcs-sombra.md).
