# 07 — Configuração

> **Estado: IMPLEMENTADO** (branch `refactor/skills-oriented-architecture`; ver [README](README.md) para as divergências de implementação). A estrutura de carga (`agents.yaml`/`config.yaml`,
> precedência de kwargs, env vars) é **reusada**. As mudanças são nos **papéis**:
> os agentes de classificação/roteamento são removidos e surgem papéis de MemGPT e
> sub-agente. Marcadores **⚠ a aprovar** indicam decisões pendentes.

A configuração vive em arquivos YAML carregados por
[config.py](../../opalacoder/config.py), além de variáveis de ambiente e flags de
CLI.

| Arquivo | Conteúdo |
|---|---|
| [agents.yaml](../../agents.yaml) | Modelos e parâmetros de LLM, por papel de agente. |
| [config.yaml](../../config.yaml) | Configuração não-agente (git, índice vetorial, etc.). |
| `<projeto>/skills.yaml` **(novo)** | Conjunto ativo de skills do projeto. Filtra quais metadados Level 1 entram no MemGPT. Ver [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml). |
| `<skill>/SKILL.md` **(novo)** | Frontmatter (`name`, `description`, `model` opcional) + instruções por skill. Ver [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai). |

`_load_yaml` procura cada arquivo em três locais (pasta do pacote, raiz do repo,
`cwd`) e usa o primeiro encontrado ([config.py:25](../../opalacoder/config.py#L25)).

---

## 1. `agents.yaml`

```yaml
default: ollama/gemma4:latest        # modelo padrão de todos os agentes
alternative: ollama/gemma4:latest    # modelo para tarefas complexas

llm_defaults:                        # defaults globais de LLM
  temperature: 1.0
  max_tokens: 8128
  num_ctx: 8192

agents:                              # overrides por papel (só os campos listados)
  orchestrator:
    num_ctx: 16384
    max_heartbeats: 20               # nº máximo de tarefas no plano
    strategy: workflow
  worker:
    num_ctx: 16384
    reasoning_effort: "none"         # ver nota abaixo
```

- `DEFAULT_MODEL` ← `default` (ou env `OPALA_MODEL`, ou `ollama/ministral-3:14b`
  como último fallback). **O valor efetivo é o de `agents.yaml`**
  ([config.py:44](../../opalacoder/config.py#L44)).
- `ALTERNATIVE_MODEL` ← `alternative` (fallback `gemini/gemini-3.1-flash-lite`).
- Precedência de kwargs por agente (`get_agent_llm_kwargs`,
  [config.py:122](../../opalacoder/config.py#L122)): override do agente >
  `llm_defaults` > defaults embutidos. Campos não-litellm
  (`model`, `max_heartbeats`, `debug`, `strategy`, `response_mode`) são removidos
  antes de ir ao litellm.

### Campos suportados por agente

`model`, `temperature`, `max_tokens`, `num_ctx`, `reasoning_effort`,
`max_heartbeats`, `heartbeats_scale_factor`, `debug`, `strategy`, `response_mode`.

### Papéis no desenho-alvo

| Papel | Estado |
|---|---|
| `memgpt` (chat-orquestrador) | **(novo)** Substitui `chat_agent`/`enricher`. Usa `max_heartbeats`, `num_ctx`, `response_mode`, `debug` e a memória clássica (ver [04](04-memoria.md)). |
| `skill_subagent` | **(novo)** Sub-agente efêmero instanciado por `run_skill`. Modelo/tier vem do campo `model` da `SKILL.md` (ver [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai)); ausente → modelo do projeto. |
| `worker` | **(reuso)** Executa comandos dentro da skill `implement-feature`. |
| `landscape_planner`, `refinement_agent`, `orchestrator` | **(reuso)** Peças internas da skill `implement-feature`. |
| ~~`intent_classifier`~~, ~~`enricher`~~, ~~`chat_agent`~~, ~~`complexity_evaluator`~~, ~~`skill_selector`~~ | **Removidos** (ver [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual)). A escolha de modelo migra para o campo `model` da `SKILL.md`; a seleção de skills, para `skills.yaml`. |

> **`reasoning_effort: "none"`** continua obrigatório para o `worker` (e qualquer
> agente que dependa de `tool_calls`) em modelos Ollama com thinking (ex. Gemma):
> com thinking ligado, a saída vai a um campo de reasoning separado e
> `tool_calls`/`content` ficam vazios (ollama issue #15288). Deixe **unset** para
> agentes que se beneficiam do raciocínio.

---

## 2. `config.yaml`

```yaml
git_strategy: auto                   # auto | hybrid | agent_driven | none
complexity_inference_mode: double    # (ver nota: inativo)
response_mode: "last"
heartbeats_scale_factor: 1

vector_index:
  embedding_model: ollama/nomic-embed-text
  embedding_fallback: sentence-transformers/all-MiniLM-L6-v2
  chunk_size: 500
  chunk_overlap: 50
  top_k: 10
```

| Chave | Efeito | Consumido em |
|---|---|---|
| `git_strategy` | Estratégia de git sombra ([05](05-vcs-sombra.md)). | `get_git_strategy` → orquestrador. |
| `response_mode` | Modo de resposta do MemGPT. | `get_agent_response_mode` → [agents.py:230](../../opalacoder/agents.py#L230) (a religar ao papel `memgpt`). |
| `heartbeats_scale_factor` | Multiplica o orçamento de sub-heartbeats do worker. | `get_agent_heartbeats_scale_factor` → script da skill `implement-feature`. |
| `vector_index.*` | Parâmetros do índice vetorial (modo bugfix da skill, [04](04-memoria.md)). | `get_vector_config` → script da skill. |

> **Knob inativo.** `complexity_inference_mode` tem getter
> (`get_complexity_inference_mode`, [config.py:73](../../opalacoder/config.py#L73))
> mas **nenhum consumidor** no código atual. **⚠ a aprovar:** removê-lo no
> redesenho ou religá-lo à seleção de modelo do sub-agente (ver
> [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual)).

---

## 3. Variáveis de ambiente

Carregadas de `.env` local e de `~/.opalacoder/.env`
([config.py:9](../../opalacoder/config.py#L9)):

| Variável | Efeito |
|---|---|
| `OPALA_MODEL` | Modelo padrão, se `default` não estiver em `agents.yaml`. |
| `OPALA_LANG` (`en`/`pt`) | Idioma da interface; senão, detectado de `LC_*`/`LANG`/locale. |
| Chaves de API (ex. `GEMINI_API_KEY`) | Resolvidas por [api_keys.py](../../opalacoder/api_keys.py) ao rotear para modelos hospedados. |

---

## 4. Flags de CLI

De `build_parser` ([cli.py:419](../../opalacoder/cli.py#L419)):

| Flag | Default | Efeito |
|---|---|---|
| `--mode {auto,plan,edit}` | `plan` | Modo de execução. |
| `--model` | `DEFAULT_MODEL` | Sobrescreve o modelo do projeto. |
| `--max-retries` | `3` | Tentativas por subpasso. |
| `--db` | `~/.opalacoder/sessions.db` | Caminho do SQLite de sessões. |
| `--lang {en,pt}` | detectado | Idioma da interface. |
| `--debug` | off | Logging completo da execução em `~/.opalacoder/logs/`. |
| `--list-projects` | — | Lista projetos e sai. |
| `--delete <nome>` | — | Apaga um projeto e sai. |
| `--version` | — | Imprime a versão e sai. |

> Em `--mode edit`, as operações em `SENSITIVE_OPS`
> ([config.py:183](../../opalacoder/config.py#L183)) — `write_file`,
> `delete_file`, `run_shell`, etc. — exigem aprovação do usuário.

---

## 5. Comandos do REPL

Registrados em [cli_commands.py](../../opalacoder/cli_commands.py):

| Comando | Descrição |
|---|---|
| `/help` (`/h`) | Mostra os comandos disponíveis. |
| `/clear` | Limpa memória e histórico do projeto. |
| `/rename <nome>` | Renomeia o projeto ativo. |
| `/list` | Lista todos os projetos. |
| `/load <nome>` | Carrega outro projeto. |
| `/delete <nome>` | Apaga um projeto. |
| `/skills` | Lista todas as skills disponíveis (ativas marcadas com `*`). |
| `/lsskills` | Lista as skills ativas no projeto. |
| `/addskill <nome>` / `/rmskill <nome>` | Adiciona/remove uma skill. |
| `/undo` | Reverte a última mudança via git sombra ([05](05-vcs-sombra.md)). |
| `/commit <msg>` | Commit manual no git sombra. |
| `/exit` (`/quit`) | Encerra a aplicação. |
