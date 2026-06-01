# 02 — MemGPT Chat-Orquestrador

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). Substitui o pipeline de classificação de intenção
> do desenho atual. Componentes **(a implementar)** ainda não existem em código.
> Marcadores **⚠ a aprovar** indicam decisões pendentes.

O ponto de entrada do sistema é um **agente MemGPT fixo** que conversa com o
usuário e orquestra a execução chamando skills. Ele **não** usa um classificador
de intenção separado: a decisão de qual skill rodar é feita pelo próprio MemGPT
via *tool-calling*.

---

## 1. O agente fixo

O MemGPT chat-orquestrador é instanciado uma vez por sessão e:

- Tem uma **skill fixa embutida — `chat-orchestrator`** (ver
  [06](06-skills-e-plugins.md#7-skills-embutidas-previstas)) que define seu
  comportamento: o que conversar e o que orquestrar.
- Carrega no system prompt os **metadados Level 1 de todas as skills** disponíveis
  (`name` + `description`), para descoberta/roteamento.
- Mantém memória no **padrão MemGPT clássico** (ver
  [04-memoria.md](04-memoria.md)).
- Expõe a tool **`run_skill(skill_name, context)`** para delegar tarefas a
  sub-agentes (ver [06 §3](06-skills-e-plugins.md#3-invocação-a-tool-run_skill)).

Composição do system prompt do MemGPT:

```
[ system prompt base do MemGPT (regras de heartbeat/tool-only/memória) ]
+ [ skill fixa chat-orchestrator: como conversar e quando orquestrar ]
+ [ metadados Level 1 de todas as skills disponíveis ]
+ [ ferramentas: run_skill, read_core_memory, append_core_memory,
    search_conversation_history ]
```

---

## 2. Loop principal

```
repl_loop()
  ├─ entrada começa com "/" → dispatch de comando (cli_commands)
  │
  └─ caso contrário → MemGPT.run(user_input)
       │
       ├─ conversa direta (saudação, pergunta, status) → send_message ao usuário
       │
       └─ pedido casa com uma skill (decisão do MemGPT) →
            run_skill(skill_name, context)
              │
              ├─ instancia sub-agente simples com a skill (ver 06 §3)
              ├─ sub-agente executa (Level 2/3) e fala com o usuário
              │     via send_message → INTERCEPTADOR (ver 06 §4)
              └─ resultado e diálogo do sub-agente entram na memória do MemGPT
       │
       └─ MemGPT retoma a conversa com consciência do que ocorreu
```

A camada Python deixa de classificar intenção e de montar `augmented_request`. O
MemGPT recebe a mensagem do usuário (com o cabeçalho de projeto injetado) e decide.

---

## 3. O que é eliminado do desenho atual

| Componente atual | Destino no desenho-alvo |
|---|---|
| `intent_classifier` (newfeat/bugfix/question/...) | **Eliminado.** O MemGPT decide via tool-calling sobre os metadados das skills. |
| Modos A/B do `chat_agent` (enricher/synthesizer) | **Absorvidos pelo MemGPT.** A recuperação de memória vira uso normal das tools `read_core_memory`/`search_conversation_history`; a síntese vira a fala natural do MemGPT após `run_skill`. |
| `_inject_project` + `augmented_request` montado em Python | O contexto vai no parâmetro `context` de `run_skill`, montado pelo MemGPT. |
| `run_pipeline` → `get_orchestrator("workflow")` | Substituído por `run_skill("implement-feature", ...)` (ver [03](03-skill-implement-feature.md)). |
| `skill_selector` — roteamento **por requisição** (`get_relevant_skills_llm`) | Absorvido pelo MemGPT (decisão via metadados Level 1). A seleção **na criação do projeto** passa a ser o `skills.yaml` ([06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml)). |
| `complexity_evaluator` | **Eliminado como agente separado.** A escolha de modelo passa para o campo `model` da `SKILL.md` (ver abaixo). |

> **Seleção dinâmica de modelo — via `SKILL.md`.** Onde antes um
> `complexity_evaluator` escolhia `default` vs `ALTERNATIVE_MODEL`
> ([cli.py:283](../../opalacoder/cli.py#L283)), agora **cada `SKILL.md` declara o
> modelo/tier do seu sub-agente** no campo opcional `model` do frontmatter
> ([06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai)).
> Ausente → modelo padrão do projeto. Skills que exigem raciocínio pesado (ex.
> `implement-feature`) podem declarar `model: alternative`.

> **`command_hint` — instrução na skill `chat-orchestrator`.** A sugestão do
> comando `/` correspondente (quando o usuário digita "clear" sem a barra) passa a
> ser uma instrução na `SKILL.md` do `chat-orchestrator`: ao receber uma mensagem
> que é só uma palavra de comando conhecida, o MemGPT sugere a forma com `/` em vez
> de orquestrar.

---

## 4. Retomada de execução (`resume`)

A retomada deixa de ser uma intenção classificada. **Implementado:** no startup, o
REPL (`repl_loop`) detecta uma execução não finalizada (campos de plano salvos no
projeto ou um checkpoint do git sombra) e, se o usuário escolher retomar, roteia
**pelo MemGPT** — chama `state.memgpt.run(...)` com uma instrução de "continuar a
implementação anterior". O MemGPT então decide chamar
`run_skill("implement-feature", ...)`. Não há mais `run_pipeline` nem agente
sintetizador separado.

Ver [03-skill-implement-feature.md](03-skill-implement-feature.md#5-retomada-e-checkpoints).
