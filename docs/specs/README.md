# Especificações do OpalaCoder — Arquitetura Orientada a Skills

> **Estado: IMPLEMENTADO.** O redesenho orientado a skills foi implementado na
> branch `refactor/skills-oriented-architecture`. Estas specs descrevem a
> arquitetura **como construída**. Os marcadores históricos do desenho —
> **(a implementar)**, **(novo)**, **(reuso)**, **(refatorar)**, **⚠ a aprovar** —
> referem-se ao processo de aprovação anterior e foram, em geral, resolvidos; onde
> ainda aparecem, são notas de origem, não trabalho pendente.

> **Divergências decididas durante a implementação** (validadas empiricamente):
> - Execução de skills com script é **claude.ai puro** (o sub-agente LLM chama
>   `run_command`), mas o request viaja por **`--request-file`** (não na linha de
>   comando) e os caminhos são **absolutos** — ver [06 §3](06-skills-e-plugins.md#3-invocação-a-tool-run_skill).
> - Motor de memória = `MemGPTAgentBlock` do framework; exige **agenticblocks ≥ 0.8.37**
>   (correção do parser de tool-call em texto) — ver [04 §1](04-memoria.md#1-memória-memgpt-clássica-do-chat-orquestrador).
> - Papel `memgpt` em `agents.yaml` (num_ctx 16384, max_heartbeats 20).
> - Retomada de execução roteada pelo MemGPT (não há mais `run_pipeline`).
> - `html-css-js` usa o script `check_contracts.py` (port de `html_css_js_tools.py`).

## Visão em uma frase

Um **agente MemGPT fixo** conversa com o usuário, mantém memória no padrão MemGPT
clássico e carrega no system prompt os **metadados (Level 1)** de todas as skills.
Quando o pedido casa com uma skill, ele chama a tool **`run_skill`**, que
instancia um **sub-agente simples** embutindo a `SKILL.md` (formato Anthropic,
*progressive disclosure* em 3 níveis). Skills complexas — como `implement-feature`
(o atual loop Planejar→Executar→Verificar) — executam seu motor como **script
Level 3 via bash**. O sub-agente fala com o usuário por ferramenta, e um
**interceptador** espelha o diálogo de volta à memória do MemGPT.

## Índice

| Spec | Conteúdo |
|---|---|
| [01-arquitetura.md](01-arquitetura.md) | Princípios, pacote `opalacoder/` (reuso/refatorar/novo), papéis e fluxo ponta a ponta. |
| [02-memgpt-orquestrador.md](02-memgpt-orquestrador.md) | MemGPT fixo, `run_skill`, o que é eliminado, retomada de execução. |
| [03-skill-implement-feature.md](03-skill-implement-feature.md) | A skill que cria/corrige código: loop reusado como script Level 3, `intent`, checkpoints. |
| [04-memoria.md](04-memoria.md) | Memória MemGPT clássica, core memory, arquival (ChromaDB), índice vetorial. |
| [05-vcs-sombra.md](05-vcs-sombra.md) | Git sombra, estratégias de VCS, checkpoints por tarefa e `/undo`. |
| [06-skills-e-plugins.md](06-skills-e-plugins.md) | **Núcleo:** formato `SKILL.md`, 3 níveis, `run_skill`, sub-agente, interceptador, segurança. |
| [07-configuracao.md](07-configuracao.md) | `agents.yaml`, `config.yaml`, papéis removidos, env vars, flags de CLI. |
| [08-ide.md](08-ide.md) | **Novo:** Integração com a IDE, protocolo JSON de stdin/stdout, servidor HTTP assíncrono e APIs REST. |


## Decisões já incorporadas

| Decisão | Onde |
|---|---|
| Skill = diretório com `SKILL.md`; frontmatter enxuto (`name`/`description` + `model` opcional); campos legados descartados | [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai) |
| Seleção de modelo do sub-agente via campo `model` da `SKILL.md` | [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai), [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual) |
| Skills obrigatórias sempre carregadas; `skills.yaml` filtra o resto (controla orçamento de tokens) | [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml) |
| Diretórios: `skills/` do projeto + `.opalacoder/skills` + `~/.opalacoder/skills` + embutidas | [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml) |
| Interceptador = wrapper na tool `send_message` | [06 §4](06-skills-e-plugins.md#4-interceptador-de-diálogo) |
| `newfeat`/`bugfix` = parâmetro `intent` único de `implement-feature` | [06 §7](06-skills-e-plugins.md#7-skills-embutidas-previstas) |
| `command_hint` = instrução na skill `chat-orchestrator` | [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual) |
| Por padrão (sem `skills.yaml`) carregam-se **todas** as skills; só `chat-orchestrator` é obrigatória | [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml) |
| Campo `model` da `SKILL.md` é **repassado ao script** (`--model`) em skills script-driven | [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai), [03 §2](03-skill-implement-feature.md#2-o-motor-loop-reusado) |
| Execução de scripts de skill entra em `SENSITIVE_OPS` (aprovação no modo `edit`) | [06 §6](06-skills-e-plugins.md#6-segurança-skills-executam-bash-sem-sandbox) |
| Motor de memória = `MemGPTAgentBlock` do framework; **remover** `opalacoder/memgpt.py` (Gemini fora de escopo) | [04 §1](04-memoria.md#1-memória-memgpt-clássica-do-chat-orquestrador) |

## Decisões pendentes — apenas detalhes de implementação

As decisões de **arquitetura** estão todas resolvidas. Restam três pontos menores,
que podem ser definidos na hora de implementar (não bloqueiam a aprovação):

| Detalhe | Onde |
|---|---|
| Detecção de checkpoint/retomada: no script da skill (recomendado) ou no REPL | [02 §4](02-memgpt-orquestrador.md#4-retomada-de-execução-resume), [03 §5](03-skill-implement-feature.md#5-retomada-e-checkpoints) |
| Refinamento de plano: via ferramenta interceptada (recomendado) ou I/O direto | [03 §4](03-skill-implement-feature.md#4-relação-com-a-fala-ao-usuário) |
| `complexity_inference_mode`: remover (recomendado) — knob inativo herdado | [07 §2](07-configuracao.md#2-configyaml) |

## Convenções

- Identificadores de código (`run_skill`, `edit_file`, `PlanOutput`, ...), nomes
  de arquivo e valores literais são mantidos em inglês.
- Citações `arquivo:linha` referem-se **apenas a código existente que será
  reusado** — componentes novos não têm linhas porque ainda não existem.
- Cada spec declara seu **estado** no topo. Aprove (ou ajuste) antes de pedir a
  implementação.
