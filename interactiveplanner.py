from agenticblocks.blocks.llm.agent import LLMAgentBlock, AgentInput
from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorBlock, CodePlanExecutorInput
from agenticblocks import as_tool

import asyncio

MAX_PULSES = 100
pulses = 0

PLANNER_MODEL="ollama/mistral-nemo"

CONFIRMATION = "Você vai receber um pedido do usuário,  crie uma visão geral do que você acha que o usuário quer! Tente decompor o problema para atender o usuário em uma lista de bullets que descrevem ações que devem ser realizadas."

DETAILMENT = """Você vai receber o plano original e um feedback do usuário e então vai refinar o plano original com base no feedback do usuário. Exemplo de entrada (próximas quatro linhas):
PEDIDO ORGINAL: Crie um html com um mensagem Olá mundo!.
PLANO ORIGIAL: criar um arquivo hello.html, inserir o texto '<html><body>Olá mundo</body></html> no hello.html.
FEEDBACK DO USUÁRIO: Olha, o html não tem título e está faltando exclamação.
Exemplo de resposta:
<html><head><title>Hello World</title></head><body><p>Olá Mundo!</p></body></html>
"""


history = []

def get_user_confirmation(question: str) -> str:
    global history, pulses
    print("#" * 30)
    print(question)
    print("#" * 30)
    history.append(f"AGENT: {question}")
    user_resp = input("Você concorda com o plano? (yes/sim para sim)")
    history.append(f"USER: {user_resp}")
    pulses += 1
    return {
        "AGENT": question,
        "USER_RESPONSE": user_resp,
        "HISTORY": "\n".join(history),
        "SYSTEM_ALERT": f"Número total de iterações {pulses}"
    }

def create_assistant(action_mode):
    return LLMAgentBlock(
        name="planner_assistent",
        description="assistente do planner",
        model=PLANNER_MODEL,
        system_prompt=action_mode
    )

def create_landscape_planner():
    return LLMAgentBlock(
        name="planner_panoramico",
        description="criador de panoramas",
        model=PLANNER_MODEL,
        system_prompt="""Você é um planejador estratégico de alto nível. Recebe uma demanda e produz um PANORAMA GERAL — não um plano detalhado, mas uma visão estruturada das grandes etapas necessárias para realizá-la.

Seu output deve:
- Listar de 3 a 7 fases ou blocos principais, em ordem lógica
- Nomear cada fase com um título curto e objetivo
- Descrever cada fase em no máximo 2 linhas: o QUE será feito, não o COMO
- Evitar detalhes técnicos, ferramentas específicas ou subetapas
- Ser claro o suficiente para que outro agente possa detalhar cada fase independentemente

Formato esperado:
1. [Nome da Fase]: [Descrição breve do que acontece nessa fase]
2. ...

Não implemente, não detalhe, não sugira código. Apenas estruture o panorama.
        """
    )

def create_plan_decomposition_agent():
    return LLMAgentBlock(
        name="decomposer",
        description="Decompõe o plano principal em subplanos executáveis",
        model=PLANNER_MODEL,
        system_prompt="""Você é um agente de decomposição de planos. Receberá um PANORAMA GERAL composto por fases de alto nível e deverá decompor cada fase em subplanos concretos e executáveis de forma independente.

Para cada fase do panorama, produza um subplano com:
- ID: identificador único no formato "SP-<número>" (ex: SP-1, SP-2)
- Fase: nome da fase do panorama a que pertence
- Objetivo: o que esse subplano entrega ao ser concluído (1 linha)
- Pré-requisitos: IDs dos subplanos que devem ser concluídos antes deste (ou "nenhum")
- Passos: lista numerada de ações concretas e atômicas (máximo 5 passos por subplano)
- Critério de conclusão: como saber que este subplano foi executado com sucesso

Regras:
- Cada subplano deve ser independente o suficiente para ser executado por um agente separado
- Os passos devem ser ações claras, não intenções vagas
- Indique a ordem de execução respeitando as dependências entre subplanos
- Não repita informações do panorama; apenas refine e concretize
- Se uma fase for simples demais, pode ser representada por um único subplano

Formato de saída para cada subplano:
---
ID: SP-<n>
Fase: <nome da fase>
Objetivo: <descrição do que entrega>
Pré-requisitos: <SP-x, SP-y ou nenhum>
Passos:
  1. <ação concreta>
  2. ...
Critério de conclusão: <como validar>
---
"""
    )

def create_executor(agent):
    return CodePlanExecutorBlock(
        executor_agent=agent,
        execution_mode="local"
    )

async def main():
    planner = create_landscape_planner()
    assistant = create_assistant(CONFIRMATION)

    plan = await planner.run(AgentInput(prompt="Crie um protótipo de aplicativo react alô mundo!"))
    result = get_user_confirmation(plan)
    prompt = f"""
        AGENT: {result['AGENT']}
        USER RESPONSE: {result['USER_RESPONSE']}
    """
    while True:
        user_confirmation = await assistant.run(AgentInput(prompt=prompt))
        resp = user_confirmation.response.strip().lower()
        if "sim" in resp:
            print("Ok, o usuário concordou com o plano, vamos continuar...")
            break
        else:
            refined_result = get_user_confirmation(user_confirmation.response)
            if pulses >= MAX_PULSES:
                print("Número máximo de iterações atingido, encerrando...")
                return
            assistant = create_assistant(DETAILMENT)
            prompt = f"""
        PEDIDO ORIGINAL: {result['AGENT']}
        PLANO ORIGINAL: {user_confirmation.response}
        FEEDBACK DO USUÁRIO: {refined_result['USER_RESPONSE']}
            """
    print("Oba! Chegamos a um acordo, irei refinar o plano e executá-lo")


    

    


if __name__ == "__main__":
    asyncio.run(main())
