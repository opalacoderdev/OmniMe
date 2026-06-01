# 06 — Skills (Núcleo do Sistema)

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). Descreve o sistema **orientado a skills** que
> substitui o roteamento por intenção. Componentes marcados **(a implementar)**
> ainda não existem em código. As decisões do mantenedor já estão incorporadas;
> restam poucos marcadores **⚠ a aprovar** em pontos menores.

No desenho atual, skills eram um mecanismo auxiliar de injeção de referência. No
desenho-alvo, **skills são a unidade central de capacidade**: um agente MemGPT
fixo conversa com o usuário e, quando o pedido casa com uma skill, **instancia um
sub-agente embutindo aquela skill** para executar a tarefa.

---

## 1. Formato de skill (padrão Anthropic / claude.ai)

Cada skill é um **diretório** contendo um `SKILL.md` e, opcionalmente, recursos e
scripts — substituindo o formato legado `<nome>.md`.

```text
skills/
└── implement-feature/
    ├── SKILL.md            # Level 1 (frontmatter) + Level 2 (corpo)
    ├── REFERENCE.md        # Level 3: instruções adicionais
    ├── scripts/
    │   └── run_workflow.py # Level 3: script executável via bash
    └── templates/          # Level 3: recursos (exemplos, schemas)
```

`SKILL.md` tem frontmatter YAML aderente ao padrão Anthropic, com **um único campo
opcional adicional** (`model`):

```yaml
---
name: implement-feature
description: Implementa uma nova funcionalidade ou corrige um bug em arquivos do
  projeto. Use quando o usuário pede para criar, adicionar, alterar ou consertar
  código.
model: alternative        # OPCIONAL: tier/modelo do sub-agente desta skill
---

# Implement Feature

## Instructions
<orientação procedural para o sub-agente>

## Scripts
Para executar o loop completo, rode:
`python scripts/run_workflow.py --request "<...>" --intent <newfeat|bugfix>`
```

Regras de campo:

- `name` (padrão Anthropic): ≤ 64 chars, apenas minúsculas/dígitos/hífen; sem
  "anthropic"/"claude".
- `description` (padrão Anthropic): não-vazio, ≤ 1024 chars; deve dizer **o que** a
  skill faz **e quando** usá-la (é o gatilho de descoberta — vira o metadado
  Level 1 no system prompt do MemGPT).
- `model` (extensão OpalaCoder, opcional): modelo/tier preferido **da execução
  desta skill**. Aceita `default`/`alternative` (mapeados para `DEFAULT_MODEL`/
  `ALTERNATIVE_MODEL`) ou um identificador litellm explícito. **Ausente → usa o
  modelo padrão do projeto.** Substitui a *seleção dinâmica de modelo* antes feita
  pelo `complexity_evaluator` — ver
  [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual).

**Propagação de `model`.** Para skills *conduzidas pelo LLM*, `model` define o
modelo do próprio sub-agente. Para skills cujo motor é um **script Level 3** (como
`implement-feature`), o sub-agente é um runner fino que apenas chama `bash` — o
raciocínio real (oráculo planejador, workers) acontece *dentro* do script, que lê
os modelos dos papéis `orchestrator`/`worker` em `agents.yaml`
([workflow_orchestrator.py:387](../../opalacoder/workflow_orchestrator.py#L387)).
Por isso, **o runner repassa o `model` ao script** (ex. `run_workflow.py --model
<valor>`), que o aplica como default desses papéis internos. Assim `model:`
funciona uniformemente — inclusive em skills baseadas em script.

Exemplo: a `SKILL.md` de `implement-feature` declara `model: alternative`; o runner
repassa `--model alternative` ao `run_workflow.py`, que o aplica aos papéis
`orchestrator`/`worker` (ver [03 §2](03-skill-implement-feature.md#2-o-motor-loop-reusado)).

> **Frontmatter enxuto.** Preserva-se o máximo do padrão claude.ai: os campos
> legados `tags`, `scope`, `tools`, `reviewer` **são descartados**. A `description`
> assume o papel de gatilho (não há mais `tags`/`scope`); ferramentas e revisores
> passam a ser **scripts/recursos Level 3** referenciados no corpo da `SKILL.md`.

---

## 2. Progressive disclosure (3 níveis)

| Nível | Quando carrega | Onde | Custo |
|---|---|---|---|
| **Level 1 — Metadata** | Sempre, no startup | `name`+`description` no system prompt do **MemGPT** | ~100 tokens/skill |
| **Level 2 — Instructions** | Quando a skill é disparada | corpo do `SKILL.md`, lido pelo **sub-agente** via bash | < 5k tokens |
| **Level 3 — Resources/Code** | Conforme necessário | arquivos do diretório, lidos/executados pelo sub-agente via bash | praticamente ilimitado (não entra no contexto se não acessado) |

A divisão-chave do OpalaCoder:

- **Level 1** vive no system prompt do **MemGPT chat-orquestrador** (descoberta/roteamento).
- **Level 2/3** são carregados pelo **sub-agente** quando `run_skill` o instancia
  — lendo `SKILL.md` e seus recursos via bash, executando scripts cujo *código
  nunca entra no contexto* (só a saída).

> **Orçamento de tokens — controlado por `skills.yaml`.** O padrão Anthropic
> assume contexto grande ("instale centenas de skills sem penalidade"); o
> OpalaCoder mira modelos locais com `num_ctx` 2048–16384, onde o Level 1 de
> *todas* as skills concorre com o prompt-base do MemGPT e a memória clássica. A
> estratégia adotada é **filtrar via `skills.yaml`** (ver §3): sem `skills.yaml`,
> carregam-se os metadados de todas as skills encontradas; **com `skills.yaml`,
> apenas as obrigatórias + as declaradas** entram nos metadados — controlando o
> orçamento naturalmente. Projetos com muitas skills devem usar `skills.yaml`.

---

## 3. Invocação: a tool `run_skill`

O MemGPT chat-orquestrador expõe uma **tool dedicada** (implementada em
[memgpt_runtime.py](../../opalacoder/memgpt_runtime.py)):

```
run_skill(skill_name: str, context: str, intent: str = "newfeat") -> str
```

Fluxo quando o MemGPT decide usar uma skill (via tool-calling):

```
MemGPT (decide pelo metadata Level 1)
   │  run_skill("implement-feature", context="<pedido + fatos>", intent="newfeat")
   ▼
camada Python (memgpt_runtime.build_run_skill_tool)
   ├─ reescopa o contexto de projeto (set_project_context) — file tools no projeto
   ├─ resolve o diretório da skill (find_skill_dir)
   ├─ grava `context` num arquivo de request fixo (.opalacoder/_skill_request_<skill>.txt)
   ├─ instancia um SUB-AGENTE simples (LLMAgentBlock) efêmero com:
   │     system prompt = SKILL.md body (Level 2) + caminhos ABSOLUTOS de scripts
   │                     + caminho do arquivo de request + intent
   │     tools = workflow tools + send_message INTERCEPTADO (ver §4)
   ├─ passa `INTENT: <intent>\n\n<context>` como prompt
   └─ sub-agente executa (lê SKILL.md, roda scripts via run_command) e produz resultado
```

- O MemGPT **não** carrega a skill para si mesmo; passa o contexto e delega.
- O **sub-agente é um `LLMAgentBlock` simples**, efêmero. Ele segue o padrão
  claude.ai puro: lê a SKILL.md (já no system prompt) e, para skills com script,
  chama `run_command` para executar o script Level 3.
- Skills complexas (ex. `implement-feature`) executam seu motor como **script
  Level 3** — ver [03-skill-implement-feature.md](03-skill-implement-feature.md).

> **Transporte do request (decidido na implementação).** O `context` pode conter
> parênteses/aspas que quebrariam o `shell=True` do `run_command` se o modelo o
> digitasse na linha de comando. Por isso o runner **grava o request num arquivo**
> e instrui o sub-agente a usar `--request-file <caminho>` (não `--request "<texto>"`).
> Os scripts (`run_workflow.py`, `check_contracts.py`) aceitam `--request-file`. Os
> caminhos de script e do request são fornecidos **absolutos** no system prompt,
> porque o diretório de trabalho do sub-agente é o do projeto, não o da skill.

---

## 4. Interceptador de diálogo

O sub-agente **fala diretamente com o usuário** por meio de uma ferramenta de
mensagem (ex. `send_message`). Para manter a memória do MemGPT coerente, um
**interceptador** captura cada interação sub-agente↔usuário e a **injeta de volta
no fluxo de conversa exposto ao MemGPT chat**:

```
sub-agente --send_message--> [INTERCEPTADOR] --> usuário (exibe)
                                   │
                                   └──> registra a troca no histórico/memória do MemGPT
```

Assim, o invariante "MemGPT é o único que fala" do desenho antigo **deixa de
valer**: o sub-agente fala, mas tudo que ele diz/recebe vira parte do contexto do
MemGPT, que retoma a conversa com plena consciência do que ocorreu.

**Mecanismo:** o interceptador é um **wrapper na ferramenta `send_message`** do
sub-agente — determinístico, independente do comportamento do modelo. Cada chamada
de `send_message` do sub-agente passa pelo wrapper, que exibe a mensagem ao usuário
**e** registra a troca no histórico/memória do MemGPT antes de retornar o controle
ao sub-agente.

---

## 5. Carregamento de skills (diretórios + `skills.yaml`)

### Diretórios de busca

O loader resolve **diretórios de skill** (cada um contendo um `SKILL.md`), nesta
ordem de prioridade:

1. `<projeto>/skills/` — skills do projeto gerenciado (se existir).
2. `<projeto>/.opalacoder/skills/` — skills locais do projeto.
3. `~/.opalacoder/skills/` — skills globais do usuário.
4. `<pacote>/skills/` — skills embutidas (obrigatórias).

> O projeto gerenciado pode trazer suas próprias skills em `skills/`, que são
> descobertas e têm os metadados carregados nos do MemGPT.

### Skills obrigatórias

A skill **`chat-orchestrator`** é **sempre carregada** (é a skill fixa do MemGPT:
conversa + orquestração), independentemente de `skills.yaml`. As demais skills são
carregadas conforme a regra de filtro abaixo.

### Filtro por `skills.yaml`

- **Sem `skills.yaml` no diretório do projeto** → carregam-se **todas** as skills
  encontradas nos diretórios de busca (metadados Level 1 de todas no MemGPT).
- **Com `skills.yaml`** → carregam-se **apenas as obrigatórias + as declaradas**
  nele. É o mecanismo de controle de orçamento de tokens (§2).

```yaml
# <projeto>/skills.yaml
skills:
  - implement-feature
  - html-css-js
```

Os comandos `/addskill` / `/rmskill` (§8) editam esse conjunto ativo.

---

## 6. Segurança (skills executam bash, sem sandbox)

Como skills rodam scripts via bash e o sandbox **não é obrigatório** nesta
arquitetura, a postura de segurança do padrão Anthropic se aplica integralmente:

- **Usar apenas skills de fontes confiáveis** (próprias ou auditadas). Uma skill
  maliciosa pode instruir o agente a executar código fora do propósito declarado.
- **Auditar todo o diretório** (SKILL.md, scripts, recursos) antes de instalar.
- **Fontes externas são risco**: skills que buscam dados de URLs podem trazer
  instruções maliciosas.
- **Execução de scripts de skill entra em `SENSITIVE_OPS`** por padrão: no modo
  `edit`, rodar o script de uma skill exige aprovação do usuário, como as demais
  operações sensíveis ([config.py:183](../../opalacoder/config.py#L183)).

---

## 7. Skills embutidas previstas

| Skill | Origem | Papel |
|---|---|---|
| `chat-orchestrator` | nova (a implementar) | Skill fixa do MemGPT: conversa + decide quando chamar `run_skill`. Ver [02](02-memgpt-orquestrador.md). |
| `implement-feature` | reusa [workflow_orchestrator.py](../../opalacoder/workflow_orchestrator.py) como script Level 3 | Loop Planejar→Executar→Verificar para criar/alterar/corrigir código. Ver [03](03-skill-implement-feature.md). |
| `html-css-js` | migra [plugins/html_css_js_tools.py](../../opalacoder/plugins/html_css_js_tools.py) | Detectores de contrato HTML/CSS/JS como scripts Level 3. |

**newfeat/bugfix:** uma **única skill `implement-feature` com um parâmetro
`intent`** (`newfeat`/`bugfix`), e não duas skills separadas. O `intent` seleciona
o prompt de planejamento e ativa (ou não) o índice vetorial — ver
[03 §3](03-skill-implement-feature.md#3-intent-newfeat-vs-bugfix).

---

## 8. Comandos de skill no REPL

Permanecem ([cli_commands.py](../../opalacoder/cli_commands.py)), adaptados ao
formato de diretório:

| Comando | Ação |
|---|---|
| `/skills` | Lista skills disponíveis (com `SKILL.md`); ativas marcadas. |
| `/addskill <nome>` / `/rmskill <nome>` | Adiciona/remove uma skill do projeto. |
