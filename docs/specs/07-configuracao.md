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

## 5. AssetStore — Repositório de Assets Reutilizáveis

> **Estado: IMPLEMENTADO**

### Conceito

A AssetStore é um **repositório local de assets reutilizáveis** empacotados com o OpalaCoder. Ela serve como banco de dados de casos bem-sucedidos de configuração para modelos locais e como biblioteca de skills extras que podem ser instaladas sob demanda em qualquer projeto.

```
opalacoder/assetstore/          ← instalado junto com o pacote pip
    skills/
        <ID>.zip                ← árvore completa da skill
        <ID>.metadata           ← metadados YAML
    modelconfigs/
        <ID>.zip                ← único arquivo .yaml de configuração
        <ID>.metadata           ← metadados YAML
```

O caminho base é sempre `Path(__file__).parent / "assetstore"`, portanto funciona corretamente quando instalado via `pip install opalacoder` em qualquer máquina.

### Formato dos metadados (`.metadata`)

Arquivo YAML com os campos:

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | ✓ | Identificador único do asset (ex: `skill_implement_feature`) |
| `type` | ✓ | `skill` ou `modelconfig` |
| `desc` | ✓ | Descrição legível usada como critério de busca |
| `name` | skill | Nome da skill (igual ao diretório dentro do zip) |
| `model` | modelconfig | Identificador do modelo (ex: `ollama/gpt-oss:latest`) |

**Exemplo — skill:**
```yaml
id: skill_implement_feature
type: skill
name: implement-feature
desc: Plan-Execute-Verify loop for implementing features and fixing bugs in project files
```

**Exemplo — modelconfig:**
```yaml
id: model_ollama_gpt_oss__latest
type: modelconfig
desc: gpt-oss:latest via Ollama — think=false, tool calling stable
model: ollama/gpt-oss:latest
```

### Destino de instalação

| Tipo | Destino no projeto |
|---|---|
| `skill` | `<projeto>/.opalacoder/skills/<name>/` |
| `modelconfig` | `<projeto>/.opalacoder/modelsconfig/<provider>/<modelo>.yaml` |

Para modelconfigs, o provider é normalizado: `ollama_chat/` e `ollama/` → diretório `ollama/`. Os dois pontos no nome do modelo viram `__`.

### Comandos REPL

```
/list_assets [tipo]           — lista todos os assets (ou só do tipo especificado)
/load_asset <tipo> <desc|id|*> — instala asset(s) no projeto ativo
```

`<desc>` pode ser o `id` exato ou o valor do campo `desc`. Usar `*` instala todos os assets do tipo.

**Exemplos:**
```
/list_assets
/list_assets modelconfig
/load_asset skill skill_implement_feature
/load_asset modelconfig model_ollama_gpt_oss__latest
/load_asset skill *
```

Após instalar uma skill, ativá-la no projeto com `/addskill <name>`.

---

## 5.1. Banco de Configurações Refinadas de Modelos

> **Estado: IMPLEMENTADO**

### Conceito

O diretório `.opalacoder/modelsconfig/` dentro de cada projeto funciona como um
**banco de dados de casos bem-sucedidos de configuração para modelos locais**. Cada
arquivo YAML registra os parâmetros que produziram comportamento correto e estável
para um modelo específico naquele projeto — resultado de testes empíricos, não de
valores genéricos.

A motivação é que modelos locais (Ollama, LM Studio, etc.) exigem combinações
precisas de parâmetros para funcionar bem: `think` e `stream` podem quebrar
tool calling em certos modelos; `num_ctx` muito baixo degrada o raciocínio;
`temperature` alta pode destabilizar modelos de instrução. Esses parâmetros
**não são portáveis** — o que funciona para `deepseek-r1:14b` não funciona para
`ministral-3:14b`. O banco de configurações resolve isso por projeto.

### Estrutura de diretórios

```
<projeto>/
└── .opalacoder/
    └── modelsconfig/
        └── <provider>/
            └── <nome_do_modelo>.yaml
```

- **`<provider>`**: prefixo do modelo, com normalização — `ollama_chat/` e `ollama/`
  mapeiam ambos para o diretório `ollama/`.
- **`<nome_do_modelo>.yaml`**: nome do modelo com `:` substituído por `__`
  (hífens mantidos).

**Exemplos de mapeamento:**

| Modelo digitado | Diretório | Arquivo |
|---|---|---|
| `ollama/deepseek-r1:14b` | `ollama/` | `deepseek-r1__14b.yaml` |
| `ollama_chat/deepseek-r1:14b` | `ollama/` | `deepseek-r1__14b.yaml` |
| `ollama/ministral-3:14b` | `ollama/` | `ministral-3__14b.yaml` |
| `ollama/qwen3:14b` | `ollama/` | `qwen3__14b.yaml` |

### Formato do arquivo YAML

O arquivo pode conter qualquer chave de `model_params` aceita pelo sistema, mais
uma chave especial `provider`:

```yaml
# .opalacoder/modelsconfig/ollama/deepseek-r1__14b.yaml
# Configuração refinada para DeepSeek-R1 14B via Ollama
# Obtida empiricamente — funciona com tool calling e thinking em tempo real

provider: ollama_chat   # opcional: substitui o prefixo do modelo na sessão
                        # aqui muda de ollama/ para ollama_chat/ para habilitar
                        # o endpoint nativo do Ollama com thinking por chunk

# LiteLLM / model_kwargs
think: true
stream: true
temperature: 0.6
num_ctx: 32768
max_tokens: 8192

# Parâmetros do agente
max_heartbeats: 15
```

```yaml
# .opalacoder/modelsconfig/ollama/ministral-3__14b.yaml
# Ministral 3 14B — sem thinking (não suportado), tool calling estável

think: false
stream: false
temperature: 0.7
num_ctx: 16384
max_tokens: 8128
max_heartbeats: 20
```

**Chave `provider`** (opcional): quando presente, substitui o prefixo do modelo
na interface. Útil para forçar `ollama_chat/` em modelos com suporte a thinking
nativo, sem o usuário precisar digitar o prefixo correto.

### Como usar

Na janela de **criação** ou **configuração** de projeto, após definir o modelo,
clique em **Load Refined Config**:

- Se existir um arquivo para o modelo: carrega e substitui completamente o
  `model_params` do projeto. Se o YAML tiver `provider:`, atualiza o campo
  modelo com o novo prefixo.
- Se não existir: exibe `--- ainda não temos parâmetros refinados para este modelo`.

O backend resolve o arquivo via `GET/POST /api/opalacoder/model-config`
([ide_server.py](../../opalacoder/ide_server.py)).

### Critério para adicionar uma entrada

Uma entrada deve ser adicionada ao banco quando:

1. O modelo foi testado com a configuração e **tool calling funciona** sem erros.
2. O comportamento de **thinking/reflection** (se aplicável) está correto.
3. Os valores de **contexto e tokens** são adequados ao hardware disponível.

O arquivo é mantido manualmente pelo usuário/equipe e versionado junto com o
projeto. Não é gerado automaticamente.

### Exemplo completo — `gpt-oss:latest` (Ollama)

```yaml
# .opalacoder/modelsconfig/ollama/gpt-oss__latest.yaml
#
# Configuração refinada para gpt-oss:latest via Ollama
# Testado em: 2026-06-02 | Hardware: RTX 4090 24GB
# Status: tool calling OK, thinking OK, stream OK
#
provider: ollama_chat   # endpoint nativo: thinking por chunk em tempo real

# LiteLLM / model_kwargs
think: false            # desativar thinking evita bug de tool_calls vazio (ollama #15288)
stream: false           # stream false: mais estável com tool calling
temperature: 0.1        # baixo para respostas determinísticas em tarefas de código
num_ctx: 32768          # contexto amplo para projetos grandes
max_tokens: 8192

# Parâmetros do agente MemGPT (chat-orquestrador)
max_heartbeats: 20
max_context_tokens: 32768

# Parâmetros do agente LLMAgentBlock (workers)
max_tool_calls: 10
debug: false
```

---

## 6. Comandos do REPL

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
