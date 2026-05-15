# ABCode

**ABCode** é um agente de codificação autônomo com planejamento interativo, execução modular e memória de sessão persistente. Projetado para funcionar bem com modelos pequenos e menos autônomos, mantendo a aparência de um agente totalmente autônomo.

---

## Funcionalidades

### Planejamento interativo
O agente recebe uma demanda em linguagem natural, gera um panorama de alto nível e entra em um loop de refinamento com o usuário até o plano ser aprovado. O plano aprovado é então decomposto automaticamente em subetapas executáveis (subplanos).

### Execução com retry
Cada subplano é executado sequencialmente, respeitando dependências entre etapas. Se uma etapa falhar, o agente tenta novamente até o limite configurável de tentativas (padrão: 3), injetando o erro anterior no contexto para que o modelo tente uma abordagem alternativa.

### Três modos de execução

| Modo   | Comportamento |
|--------|---------------|
| `plan` | Gera o plano e pede aprovação do usuário antes de executar (padrão) |
| `auto` | Executa tudo sem interrupções — ideal para pipelines automatizados |
| `edit` | Pede confirmação do usuário apenas para operações sensíveis (criação/deleção de arquivos, chamadas de rede, etc.) |

### Sessões persistentes
Cada execução pertence a uma sessão nomeada. Todo o estado — demanda, plano, subplanos, resultados e histórico de conversa — é salvo em um banco SQLite local (`~/.abcode/sessions.db`). Ao retomar uma sessão existente, o usuário pode escolher entre continuar de onde parou ou recomeçar do zero.

### Terminal elegante
Saída formatada com [Rich](https://github.com/Texel-io/rich): banners, spinners de progresso, painéis de plano, tabela de status por subplano e relatório de erros destacado.

### Arquitetura modular
O código é dividido em módulos independentes e fáceis de depurar:

```
abcode/
├── config.py       configurações globais (modelo, retries, modo, db)
├── terminal.py     output Rich (banners, spinners, painéis, tabelas)
├── session.py      gerenciamento de sessões SQLite
├── subplan.py      modelo Subplan, parser de saída LLM, sort topológico
├── agents.py       factories dos agentes LLM
├── planner.py      pipeline: panorama → refinamento → decomposição
├── executor.py     execução com retry e gating por modo
└── cli.py          argparse + bootstrap de sessão + orquestração
```

---

## Requisitos

- Python 3.11+
- [agenticblocks](https://github.com/gilzamir/agenticblocks) instalado no ambiente virtual
- [Rich](https://github.com/Texel-io/rich): `pip install rich`
- Um servidor LLM acessível (ex.: [Ollama](https://ollama.com) com `mistral-nemo`, ou qualquer modelo suportado pelo [litellm](https://docs.litellm.ai))

---

## Instalação

```bash
# Clone o repositório
git clone <url-do-repositorio>
cd ABCode

# Crie e ative o ambiente virtual
python -m venv .env
source .env/bin/activate          # Linux/macOS
# .env\Scripts\activate           # Windows

# Instale as dependências
pip install agenticblocks rich python-dotenv
```

### Variáveis de ambiente (opcional)

Crie um arquivo `.env` na raiz do projeto para sobrescrever os padrões:

```env
# Modelo LLM padrão (qualquer string suportada pelo litellm)
ABCODE_MODEL=ollama/mistral-nemo
```

---

## Como executar

```bash
# Ative o ambiente virtual
source .env/bin/activate

# Execução padrão (modo plan)
python main.py

# Escolher o modo de execução
python main.py --mode auto
python main.py --mode plan
python main.py --mode edit

# Usar outro modelo
python main.py --model ollama/llama3

# Aumentar o número de tentativas por subplano
python main.py --max-retries 5

# Banco de dados em caminho customizado
python main.py --db /caminho/para/sessoes.db

# Ver versão
python main.py --version

# Ajuda
python main.py --help
```

---

## Fluxo de uma sessão

```
1. Banner + escolha do modo
       ↓
2. Nome da sessão
   ├── Nova sessão  → prossegue
   └── Existente   → retomar ou sobrescrever
       ↓
3. Usuário digita a demanda
       ↓
4. Agente gera panorama (plano de alto nível)
       ↓
5. Loop de refinamento (modos plan/edit)
   ├── Usuário aprova → avança
   └── Usuário sugere mudanças → agente refina e volta ao passo 5
       ↓
6. Decomposição em subplanos (SP-1, SP-2, …)
       ↓
7. Execução sequencial por dependência
   └── Para cada subplano:
       ├── (edit) operação sensível? → pede confirmação
       ├── Executa o código gerado
       ├── Sucesso → próximo subplano
       └── Falha → retry até max_retries, então notifica erro
       ↓
8. Agregação: síntese final integrada de todos os resultados
       ↓
9. Resultado exibido + sessão salva
```

---

## Exemplos de uso

```
$ python main.py --mode plan

    _    ____  ____          _
   / \  | __ )/ ___|___   __| | ___
  / _ \ |  _ \ |   / _ \ / _` |/ _ \
 / ___ \| |_) | |__| (_) | (_| |  __/
/_/   \_\____/ \____\___/ \__,_|\___|

  version 0.1.0  mode: plan

─────────────────── Sessão ─────────────────────
Sessões existentes:
  meu-projeto   2025-05-15  mode=plan

? Nome da sessão
  → novo-projeto

? Qual é a demanda de codificação?
  → Criar uma API REST em FastAPI com CRUD de usuários e banco SQLite

─────────────────── Fase 1 — Panorama ──────────
💭 Gerando panorama do plano…
╭─────────────── Plano Gerado ──────────────────╮
│ 1. Estrutura do Projeto: Criar pastas e        │
│    arquivos base (main.py, models.py, etc.)    │
│ 2. Modelo de Dados: Definir esquema SQLite      │
│ ...                                            │
╰───────────────────────────────────────────────╯

? O plano está ok? → sim
✓ Plano aprovado!
...
```

---

## Configuração avançada

### Alterar o modelo padrão

Edite `abcode/config.py`:

```python
DEFAULT_MODEL = "ollama/mistral-nemo"  # altere aqui
```

Ou use a variável de ambiente `ABCODE_MODEL`.

### Alterar o número padrão de retentativas

```python
DEFAULT_MAX_RETRIES = 3  # em abcode/config.py
```

Ou passe `--max-retries N` na linha de comando.

### Adicionar operações sensíveis customizadas

Em `abcode/config.py`:

```python
SENSITIVE_OPS = {
    "write_file", "delete_file", "run_shell",
    "send_network_request", "create_user", "delete_user",
    # adicione aqui palavras-chave de operações que devem pedir confirmação no modo edit
}
```

---

## Segurança

- O modo `edit` exige confirmação explícita para operações que afetam o sistema de arquivos, a rede ou contas de usuário.
- Código gerado é executado localmente via `exec()` (modo `local`). Para maior isolamento, o `CodePlanExecutorBlock` da biblioteca AgenticBlocks suporta execução em contêiner Docker — edite `make_executor_block` em `abcode/agents.py` trocando `execution_mode="local"` por `execution_mode="docker"`.
- Nunca execute o agente em modo `auto` com acesso a sistemas de produção sem revisar os subplanos gerados.

---

## Licença

MIT
