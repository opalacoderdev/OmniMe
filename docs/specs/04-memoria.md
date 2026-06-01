# 04 — Memória

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). A memória do MemGPT chat-orquestrador
> (ver [02](02-memgpt-orquestrador.md)) deve seguir o **padrão MemGPT clássico**.
> Marcadores **⚠ a aprovar** indicam decisões pendentes.

A pilha de memória do OpalaCoder tem quatro camadas, com propósitos distintos:

| Camada | Onde | Para quê |
|---|---|---|
| Contexto de trabalho (MemGPT clássico) | em memória, no MemGPT chat-orquestrador | Janela de contexto gerenciada: main context + resumo recursivo + memória externa via tools. |
| Core memory | coluna `core_memory` em `sessions.db` | Fatos rápidos e persistentes sobre o projeto. |
| Memória arquival | ChromaDB em `~/.opalacoder/chroma/` | Busca semântica sobre conversas e logs passados. |
| Índice vetorial | `<projeto>/.opalacoder/vector_index.sqlite` | Recuperação de chunks de código pela skill `implement-feature` (modo bugfix). |

---

## 1. Memória MemGPT clássica do chat-orquestrador

O MemGPT chat-orquestrador deve implementar a gestão de contexto do **artigo
clássico MemGPT**: um *main context* limitado (working memory), evicção FIFO das
mensagens mais antigas, condensação em um **resumo recursivo** reinjetado como
mensagem de sistema, alertas de **pressão de memória**, e acesso à memória externa
via ferramentas.

**Motor: `MemGPTAgentBlock` do framework agenticblocks** (como implementado). O
`MemGPTAgentBlock` do framework já implementa todo o comportamento clássico:
evicção FIFO (`_get_safe_eviction_index`), resumo recursivo (`_summarize`),
limiares `eviction_threshold`/`memory_pressure_threshold` — mais
`response_schema`/`response_mode`. É instanciado por `build_chat_orchestrator`
([memgpt_runtime.py](../../opalacoder/memgpt_runtime.py)). A classe local
`OpalaMemGPTAgentBlock` foi **removida** (`opalacoder/memgpt.py` não existe mais),
junto com o trace `~/.opalacoder/memgpt_trace.log` que só ela gravava.

> **Correção necessária no framework (≥ 0.8.37).** Durante a implementação, um teste
> de 2–3 turnos contra o gemma4 expôs uma falha: a partir do 2º turno o modelo
> passa a emitir as chamadas de ferramenta como **JSON-em-texto no formato aninhado**
> `{"tool_calls":[{"function":{"name",...}}]}` em vez de usar a API nativa. O parser
> de recuperação do `MemGPTAgentBlock` só entendia o formato achatado → rejeitava →
> a mensagem malformada poluía o histórico → o modelo imitava o próprio erro até
> esgotar os heartbeats (resposta vazia). Corrigido **no agenticblocks**: o bloco
> passou a reusar o parser compartilhado `_json_to_tool_calls` (que trata o formato
> aninhado e valida os nomes contra as tools registradas) e a neutralizar a mensagem
> malformada no histórico. Por isso o OpalaCoder **exige agenticblocks ≥ 0.8.37**
> (pin em `requirements.txt`); uma versão anterior reintroduz o bug de resposta vazia.

> **Ressalva (Gemini).** Gemini não é alvo nesta fase, embora `ALTERNATIVE_MODEL`
> aponte por padrão para um modelo Gemini. O saneamento de sequências Gemini que a
> classe local tinha **não** foi portado; se o chat-orquestrador vier a rodar em
> Gemini, esse saneamento precisará ser adicionado ao bloco do framework.

O MemGPT chat-orquestrador também carrega, no system prompt, os **metadados Level
1 das skills** (ver [06 §2](06-skills-e-plugins.md#2-progressive-disclosure-3-níveis)) —
o que concorre com o orçamento de contexto da memória clássica. Ver o marcador de
orçamento de tokens em [06 §2](06-skills-e-plugins.md#2-progressive-disclosure-3-níveis).

### Ferramentas de memória do MemGPT

| Ferramenta | Uso |
|---|---|
| `read_core_memory` | Lê os fatos rápidos do projeto. |
| `append_core_memory` | Grava fatos novos permanentemente (após uma skill executar). |
| `search_conversation_history` | Busca semântica na memória arquival. |

> Estas três ferramentas já existem em [tools.py](../../opalacoder/tools.py). Os
> antigos **Modo A (enricher) / Modo B (synthesizer)** do `chat_agent`
> desaparecem: recuperar memória vira uso normal destas tools pelo MemGPT, e a
> síntese vira a fala natural do MemGPT após `run_skill` (ver [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual)).

---

## 2. Core memory

String persistente por projeto, na coluna `core_memory` de `sessions.db`
(migração em [project.py:54](../../opalacoder/project.py#L54); campo em
`ProjectData`). Guarda fatos compactos — arquivos criados/modificados, stack,
decisões. O MemGPT a lê para contextualizar a conversa e a atualiza (via
`append_core_memory`) após uma skill concluir trabalho relevante.

> O core memory **não** deve ser despejado cru no contexto de um sub-agente de
> skill: o MemGPT seleciona os fatos relevantes e os passa via o parâmetro
> `context` de `run_skill` (ver [06 §3](06-skills-e-plugins.md#3-invocação-a-tool-run_skill)).
> Despejar o core memory cru inundaria modelos de contexto pequeno.

---

## 3. Memória arquival (`archival.py` + ChromaDB)

Fonte: [archival.py](../../opalacoder/archival.py). Armazena mensagens para busca
por similaridade de cosseno via ChromaDB persistente em `~/.opalacoder/chroma/`.

- Cliente singleton (`_get_chroma_client`), uma coleção por projeto (nome
  sanitizado para alfanumérico).
- `append_to_archival(project, message_id, role, content, timestamp)` — adiciona
  um documento com metadados.
- `search_archival(project, query, limit=5)` — retorna os documentos mais
  similares, com `role` e `timestamp`.
- `clear_archival(project)` — apaga a coleção do projeto.

É a camada por trás de `search_conversation_history`, usada pelo MemGPT
chat-orquestrador para recuperar trabalho passado relevante.

---

## 4. Índice vetorial (`vector_index.py`)

Fonte: [vector_index.py](../../opalacoder/vector_index.py). **Usado apenas pela
skill `implement-feature` em modo bugfix** (ver
[03 §3](03-skill-implement-feature.md#3-intent-newfeat-vs-bugfix)); hoje invocado em
[workflow_orchestrator.py:1339](../../opalacoder/workflow_orchestrator.py#L1339),
que passa a ser o script Level 3 dessa skill.

- **Chunking**: cada arquivo de texto do projeto é fatiado em janelas
  sobrepostas de linhas (`chunk_size`/`chunk_overlap`); cada janela vira um
  `Chunk`.
- **Embedding**: via `litellm` (Ollama, ex. `nomic-embed-text`) com fallback para
  `sentence-transformers`.
- **Armazenamento**: SQLite em `<projeto>/.opalacoder/vector_index.sqlite`;
  embeddings como arrays JSON.
- **Build incremental**: re-embeda só arquivos alterados por `mtime` (ou se
  `chunk_size`/`chunk_overlap` mudaram); remove chunks de arquivos apagados.
- **Recuperação**: `retrieve(query, top_k)` calcula cosseno em memória contra
  todos os chunks e retorna os top-K.
- **Formatação**: `format_for_prompt(ranked)` monta o bloco injetado no prompt do
  planejador de bugfix, com `arquivo (linhas i–j, score)`.

Parâmetros (`chunk_size`, `chunk_overlap`, `top_k`, modelos de embedding) vêm de
`get_vector_config()` / `config.yaml` — ver [07-configuracao.md](07-configuracao.md).

> **Distinção.** O **índice vetorial** (acima) recupera *chunks de código* para
> localizar bugs. O **code index** ([code_index.py](../../opalacoder/code_index.py))
> é um índice de *símbolos* (funções/classes) usado para enriquecer o snapshot do
> projeto no planejamento e responder `find_symbol`/`find_callers`. São
> subsistemas separados.
