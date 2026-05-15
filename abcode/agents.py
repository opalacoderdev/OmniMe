"""Agent factory functions for ABCode."""

from agenticblocks.blocks.llm.agent import LLMAgentBlock
from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorBlock

from .config import DEFAULT_MODEL


def _make_llm(name: str, system_prompt: str, model: str, **kwargs) -> LLMAgentBlock:
    return LLMAgentBlock(
        name=name,
        description=name,
        model=model,
        system_prompt=system_prompt,
        **kwargs,
    )


def make_landscape_planner(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "landscape_planner",
        """Você é um planejador estratégico de alto nível. Recebe uma demanda e produz um PANORAMA GERAL.

Seu output deve:
- Listar de 3 a 7 fases principais em ordem lógica
- Nomear cada fase com um título curto
- Descrever cada fase em no máximo 2 linhas (O QUÊ, não o COMO)
- Evitar detalhes técnicos ou subetapas

ATENÇÃO: Toda fase gerada será enviada a um executor autônomo que escreve e roda scripts Python. Não crie fases abstratas como 'Análise de Requisitos' ou 'Escolha de Ferramentas'. Crie apenas fases de IMPLEMENTAÇÃO TÉCNICA (ex: 'Baixar dados', 'Processar dados'). Inclua a validação dentro da própria fase de criação, não como uma fase separada.

Formato de saída:
1. [Nome da Fase]: [Descrição breve]
2. ...

Não implemente, não detalhe, não sugira código.
""",
        model=model,
    )


def make_confirmation_agent(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "confirmation_agent",
        """Você receberá:
AGENT: <PLANO ATUAL>
USER_RESPONSE: <RESPOSTA DO USUÁRIO>

Sua tarefa: determinar se o usuário APROVOU o plano ou quer MODIFICÁ-LO.

Responda SOMENTE com uma única palavra: "sim" ou "não".

Regras estritas:
- Responda "sim" APENAS se o usuário expressou aprovação clara e sem condições.
  Exemplos de aprovação: "sim", "ok", "aprovado", "pode prosseguir", "tudo certo", "perfeito".
- Responda "não" se o usuário pediu qualquer alteração, adição, remoção ou correção,
  mesmo que de forma educada ou parcial.
  Exemplos de NÃO aprovação: "quero que...", "adicione...", "remova...", "mude...",
  "somente mostre...", "não precisa de...", "o app deve...".

Não explique, não acrescente nada. Apenas: sim ou não.
""",
        model=model,
    )


def make_refinement_agent(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "refinement_agent",
        """Você receberá o plano original e um feedback do usuário e vai refinar o plano com base nesse feedback.

Entrada:
PEDIDO ORIGINAL: <pedido>
PLANO ORIGINAL: <plano>
FEEDBACK DO USUÁRIO: <feedback>

Saída: o plano refinado, mantendo o mesmo formato do plano original.
""",
        model=model,
    )


def make_decomposer(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "decomposer",
        """Você é um agente de decomposição de planos. Receberá um PANORAMA GERAL e decompõe cada fase em subplanos executáveis.

Para cada fase, produza:
---
ID: SP-<n>
Fase: <nome da fase>
Objetivo: <o que entrega>
Pré-requisitos: <SP-x, SP-y ou nenhum>
Passos:
  1. <ação concreta>
  2. ...
Critério de conclusão: <como validar>
---

Regras:
- Cada subplano deve ser executável por um agente gerador de código Python (um script autossuficiente).
- Agrupe a criação do código e seus testes no mesmo subplano (NÃO crie um subplano separado apenas para testes ou validação).
- Não crie subplanos de planejamento, análise teórica ou "escolha de ferramentas". Foque na execução de código.
- Passos devem ser ações claras e atômicas (máximo 5 por subplano).
- Respeite dependências entre subplanos.
""",
        model=model,
        litellm_kwargs={"num_ctx": 32000},
    )


def make_aggregator(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "aggregator",
        """Você é um sintetizador de resultados. Receberá o pedido original e os resultados de cada subplano executado.
Produza uma resposta coesa e completa que integre todos os resultados, respondendo ao pedido original.
Seja direto e objetivo. Se houve erros em algum subplano, mencione-os brevemente.
""",
        model=model,
    )


def make_executor_block(model: str = DEFAULT_MODEL) -> CodePlanExecutorBlock:
    executor_agent = _make_llm(
        "executor_agent",
        "Você é um agente executor. Recebe uma tarefa e gera código Python para realizá-la.",
        model=model,
    )
    return CodePlanExecutorBlock(
        executor_agent=executor_agent,
        execution_mode="local",
    )


def make_skill_selector(model: str = DEFAULT_MODEL) -> LLMAgentBlock:
    return _make_llm(
        "skill_selector",
        """Você é um roteador semântico. Sua função é analisar um pedido do usuário e decidir quais Skills (habilidades/regras) são necessárias.

Você receberá:
DEMANDA DO USUÁRIO: <texto>
SKILLS DISPONÍVEIS:
- nome_da_skill: descrição da skill
...

Com base na demanda, liste os nomes exatos das skills que você julga serem relevantes para o sucesso da tarefa.
Responda APENAS com os nomes das skills, separados por vírgula. Se nenhuma for relevante, responda 'nenhuma'.
""",
        model=model,
    )
