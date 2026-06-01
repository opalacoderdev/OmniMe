# 01 — Arquitetura

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). Componentes
> marcados **(a implementar)** ainda não existem em código. Marcadores **⚠ a
> aprovar** indicam decisões pendentes de confirmação do mantenedor. Onde uma
> spec cita código existente, é porque ele será **reusado**.

Visão geral dos componentes do OpalaCoder e do fluxo de uma requisição, da
entrada do usuário até a resposta.

---

## 1. Princípios

- **Centrado em projeto.** Toda interação acontece dentro de um projeto nomeado com um caminho de filesystem fixo. Isso ancora o contexto do LLM, escopa todas as operações de arquivo/terminal àquele diretório e persiste o histórico.

- **Orientado a skills.** Um **agente MemGPT fixo** conversa com o usuário e
  orquestra. Quando o pedido casa com uma skill, ele instancia um **sub-agente
  embutindo aquela skill** (formato e *progressive disclosure* no padrão
  Anthropic/claude.ai). Ver [06-skills-e-plugins.md](06-skills-e-plugins.md).

- **Otimizado para modelos locais pequenos.** Skills complexas executam seu motor
  como **script (Level 3) via bash**, mantendo a lógica pesada determinística em
  Python em vez de depender do LLM para conduzi-la.

- **Construído sobre AgenticBlocks.IO.** Os agentes são `LLMAgentBlock` /
  `MemGPTAgentBlock` do framework [agenticblocks](https://github.com/gilzamir/agenticblocks).

---

## 2. Pacote `opalacoder/`

Legenda: **(reuso)** código atual reaproveitado · **(refatorar)** muda de papel ·
**(novo)** a implementar.

| Módulo | Responsabilidade no desenho-alvo |
|---|---|
| [cli.py](../../opalacoder/cli.py) | **(refatorar)** Entrypoint, menu de projeto, REPL. Deixa de classificar intenção e de montar `run_pipeline`; delega ao MemGPT chat-orquestrador. |
| `memgpt_runtime` | **(novo)** MemGPT fixo, tool `run_skill`, instanciação do sub-agente e interceptador de diálogo. Ver [02](02-memgpt-orquestrador.md), [06](06-skills-e-plugins.md). |
| [memgpt.py](../../opalacoder/memgpt.py) | **(remover)** `OpalaMemGPTAgentBlock` — substituído pelo `MemGPTAgentBlock` do framework; só agregava compatibilidade Gemini, fora do escopo (ver [04 §1](04-memoria.md#1-memória-memgpt-clássica-do-chat-orquestrador)). |
| [skills.py](../../opalacoder/skills.py) | **(refatorar)** Loader resolve **diretórios** com `SKILL.md` (formato Anthropic) e expõe metadados Level 1. |
| [workflow_orchestrator.py](../../opalacoder/workflow_orchestrator.py) | **(reuso)** Loop Planejar→Executar→Verificar vira o **script Level 3** da skill `implement-feature` (ver [03](03-skill-implement-feature.md)). |
| [planner.py](../../opalacoder/planner.py) | **(reuso)** Panorama + refinamento, dentro da skill `implement-feature`. |
| [workflow_tools.py](../../opalacoder/workflow_tools.py) | **(reuso)** Ferramentas do worker: `edit_file`, `read_file`, `find_symbol`, `send_message`. |
| [tools.py](../../opalacoder/tools.py) | **(reuso)** Ferramentas base + de memória (`read/append_core_memory`, `search_conversation_history`). |
| [vcs.py](../../opalacoder/vcs.py) | **(reuso)** Estratégias de git sombra (ver [05](05-vcs-sombra.md)). |
| [archival.py](../../opalacoder/archival.py) | **(reuso)** Memória arquival por similaridade (ChromaDB). |
| [code_index.py](../../opalacoder/code_index.py) | **(reuso)** Índice de símbolos (tree-sitter + fallback regex, SQLite). |
| [vector_index.py](../../opalacoder/vector_index.py) | **(reuso)** Índice vetorial de chunks (modo bugfix da skill). |
| [embeddings.py](../../opalacoder/embeddings.py) | **(reuso)** Backends de embedding. |
| [plugins/](../../opalacoder/plugins/) | **(refatorar)** `html_css_js_tools` migra para scripts Level 3 de uma skill. |
| [project.py](../../opalacoder/project.py) | **(reuso)** Persistência de projetos em SQLite. |
| [config.py](../../opalacoder/config.py) | **(refatorar)** Remove papéis de classificador/avaliador; ver [07](07-configuracao.md). |
| [agents.py](../../opalacoder/agents.py) | **(refatorar)** Remove classificador/enricher/synthesizer; mantém MemGPT e worker. |
| [orchestrator.py](../../opalacoder/orchestrator.py) | **(refatorar)** Registro de estratégias — pode ser absorvido pelo script da skill. |
| [cli_commands.py](../../opalacoder/cli_commands.py) · [structured.py](../../opalacoder/structured.py) · [i18n.py](../../opalacoder/i18n.py) · [terminal.py](../../opalacoder/terminal.py) · [api_keys.py](../../opalacoder/api_keys.py) | **(reuso)** Comandos `/...`, saída estruturada, i18n, saída Rich, chaves de API. |
| [ide_server.py](../../opalacoder/ide_server.py) | **(novo)** Servidor assíncrono HTTP e API REST que serve a GUI React e expõe comandos. |
| [agent_stdin.py](../../opalacoder/agent_stdin.py) | **(novo)** Protocolo bidirecional JSON stdin/stdout para controle remoto de agentes. |


---

## 3. Papéis de agente

| Papel | Função no desenho-alvo |
|---|---|
| **MemGPT chat-orquestrador** | Agente fixo de entrada: conversa, mantém memória clássica e decide chamar skills via `run_skill`. Skill fixa `chat-orchestrator`. Ver [02](02-memgpt-orquestrador.md). |
| **sub-agente de skill** | `LLMAgentBlock` efêmero instanciado por `run_skill`; carrega `SKILL.md` (Level 2/3) e executa. Ver [06 §3](06-skills-e-plugins.md#3-invocação-a-tool-run_skill). |
| `worker` | **(reuso)** `LLMAgentBlock` que executa cada comando de tarefa com ferramentas, dentro do script da skill `implement-feature`. |
| ~~`intent_classifier`~~ | **Eliminado.** O MemGPT roteia via tool-calling, sem classificação separada. |
| ~~`complexity_evaluator`~~ | **Eliminado.** A escolha de modelo passa para o campo `model` da `SKILL.md` ([06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai)). |
| ~~`skill_selector`~~ | **Eliminado.** Roteamento por requisição → MemGPT; seleção do conjunto ativo → `skills.yaml` ([06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml)). |
| ~~`chat_agent` (Modos A/B)~~ | **Absorvido** pelo MemGPT chat-orquestrador. |
| `landscape_planner`, `refinement_agent`, `orchestrator` | **(reuso)** Permanecem como peças internas da skill `implement-feature`. |

> **A fala ao usuário muda.** No desenho atual só o `chat_agent` falava. No
> desenho-alvo, o **sub-agente de skill fala diretamente** (via ferramenta), mas
> um **interceptador** espelha toda a troca de volta na memória do MemGPT, que
> retoma a conversa consciente do que ocorreu. Ver
> [06 §4](06-skills-e-plugins.md#4-interceptador-de-diálogo).

> **Seleção de skills do projeto — via `skills.yaml`.** O subconjunto ativo de
> skills (que define quais metadados Level 1 entram no MemGPT) é declarado num
> `skills.yaml` no diretório do projeto. Sem `skills.yaml`, carregam-se todas as
> skills encontradas; com ele, só as obrigatórias + as declaradas. Substitui o
> antigo `select_skills_for_project`. Ver
> [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml).

---

## 4. Fluxo ponta a ponta

```
main() → startup_menu()        ← cria/carrega projeto, descobre skills (metadados Level 1)
  │
  └─ repl_loop()               ← define contexto de projeto, instancia o MemGPT fixo
       │
       ├─ entrada começa com "/" → dispatch de comando (cli_commands)
       │
       └─ caso contrário → MemGPT.run(user_input)
            │
            ├─ conversa direta (saudação, pergunta, status) → fala ao usuário
            │
            └─ pedido casa com uma skill → run_skill(skill_name, context)
                 │
                 ├─ instancia sub-agente simples com a skill
                 ├─ sub-agente lê SKILL.md (Level 2) e recursos/scripts (Level 3) via bash
                 ├─ sub-agente executa e fala ao usuário → INTERCEPTADOR → memória do MemGPT
                 └─ resultado volta ao MemGPT
            │
            └─ MemGPT retoma a conversa e grava fatos novos (append_core_memory)
```

O roteamento (MemGPT + `run_skill`) está em
[02-memgpt-orquestrador.md](02-memgpt-orquestrador.md); a skill que cria/corrige
código está em [03-skill-implement-feature.md](03-skill-implement-feature.md); o
formato e o carregamento de skills, em [06-skills-e-plugins.md](06-skills-e-plugins.md).

---

## 5. Armazenamento em disco

| Caminho | Conteúdo |
|---|---|
| `~/.opalacoder/sessions.db` | SQLite de projetos e histórico (`DEFAULT_DB_PATH`, configurável com `--db`). |
| `~/.opalacoder/chroma/` | Coleções ChromaDB da memória arquival, uma por projeto. |
| `~/.opalacoder/.env` | `.env` global (carregado além do `.env` local). |
| `~/.opalacoder/logs/run_<ts>.log` | Log completo de execução quando `--debug` está ativo. |
| ~~`~/.opalacoder/memgpt_trace.log`~~ | **Deixa de existir** — só o `OpalaMemGPTAgentBlock` (a remover) gravava esse trace; o motor adotado é o do framework (ver [04 §1](04-memoria.md#1-memória-memgpt-clássica-do-chat-orquestrador)). |
| `<projeto>/.opalacoder/.git` | Repositório git sombra do projeto (ver [05](05-vcs-sombra.md)). |
| `<projeto>/.opalacoder/vector_index.sqlite` | Índice vetorial de chunks do projeto. |
| `<projeto>/.opalacoder/` (code index) | Índice de símbolos em SQLite. |
| `<projeto>/plan.md` | Último plano aprovado, salvo pelo orquestrador. |
