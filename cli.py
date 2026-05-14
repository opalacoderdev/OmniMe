from agenticblocks.blocks.llm.agent import LLMAgentBlock, AgentInput
from agenticblocks.blocks.patterns.code_plan_executor import CodePlanExecutorBlock, CodePlanExecutorInput
from agenticblocks import as_tool

import asyncio

MAX_PULSES = 100
pulses = 0

PLANNER_MODEL="gemini/gemini-3-flash-preview"
PLANNER_SYSTEM_PROMPT=f"""
Você não responderá direito à sua entrada,
em vez disso, deve criar um plano de código em python
que realiza o que a entrada indica. 
Por exemplo, se alguém te pedir quanto é 2+2,
em vez de responder 4, gere um programa em python
que calcula e imprime o resultado.

IMPORTANTE: 
    1. PRODUZA APENAS O CÓDIGO NA SÁIDA.
    2. ANTES DE ENVIAR O PLANO, 
    CONSULTE O USUÁRIO, POR MEIO DA FERRAMENTA check_user,
    SE ELE CONCORDA COM O PLANO. PARA ISSO,
    ENVIE UM PLANO PARA check_user (que aceita uma string).
    SE O USUÁRIO DIZER QUE NÃO E ELE NÃO DIZER O MOTIVO,
    PEÇA MAIS INFORMAÇÕES AO USUÁRIO E GERE UM NOVO 
    PLANO COM AS NOVAS INFORMAÇÕES E A INFORMAÇÃO ORIGINAL,
    REPETINDO PROCESSO DE CONFIRMAÇÃO DO USUÁRIO. SOMENTE
    PARE SE O USUÁRIO DIZER QUE QUER TERMINAR OU QUE DESISTIU.
    SE O USUÁRIO DIZER QUE SIM, GERE O PLANO E O RETORNE.
    3. O PALNO DEVE TER APENAS CÓDIGO, NADA DE APRESENTAÇÕES
    OU COMENTÁRIOS FORA DO CÓDIGO. POR EXEMPLOS, SE O USUÁRIO
    PERGUNTAR QUANTO É 2+2, NÃO RESPONDA DIRETAMENTE, 
    GERE O CÓDIGO QUE PRODUZ A RESPOSTA, COMO EM:
        print(f"2+2 = {2+2}").
    4. INICIALMENTE VOCÊ TEM UMA QUANTIDADE MÁXIMA DE PULSOS,
    UM PULSO TE DÁ DIREITO DE UMA AÇÃO. POR ISSO,
    SE VOCÊ TEM APENAS UM PULSO, DEVE USAR O PULSO
    PARA GERAR A RESPOSTA FINAL. A QUANTIDADE INICIAL
    DE PULSOS É DE {MAX_PULSES}.
"""

ASSISTENT_MODEL = "ollama/mistral-nemo"
ASSISTENT_PROMPT = """
Você executa tarefas diversas, como resumir
reescrever uma frase e mandar uma resposta 
para alguém.
"""

history = []

@as_tool
def check_user(question: str) -> str:
    global history
    print("#" * 30)
    print(question)
    print("#" * 30)
    history.append(f"AGENT: {question}")
    user_resp = input("Você concorda com o plano?")
    history.append(f"USER: {user_resp}")
    pulses += 1
    return f"""
        AGENT: {question} \n
        USER RESPONSE: {user_resp} \n\n
        HISTORY: {"\n".join(history)} \n\n
        SYSTEM ALERT: Número total de pulsos restantes {100-pulses}
    """

def create_planner():
    return LLMAgentBlock(
        name="cli_planner",
        description="planning response to user questions",
        model=PLANNER_MODEL,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        tools=[check_user],
        debug=True,
        max_tool_calls=MAX_PULSES
    )

def create_executor(agent):
    return CodePlanExecutorBlock(
        executor_agent=agent,
        execution_mode="local"
    )

async def main():
    planner = create_planner()
    executor = create_executor(planner)
    result = await executor.run(CodePlanExecutorInput(task="Crie um documento html chamado hello.html que mostra hello world"))   
    print("-" * 30)
    print(f"Sucesso: {result.success}")
    print(f"\nCódigo Gerado pelo LLM:\n{result.code_generated}")
    print(f"\nStdout da Execução:\n{result.execution_stdout.strip()}")
    if result.execution_stderr:
        print(f"\nStderr da Execução:\n{result.execution_stderr.strip()}")
    print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
