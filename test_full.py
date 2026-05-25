import asyncio
from opalacoder.project import ProjectStore
from opalacoder.agents import make_chat_memgpt_agent, make_intent_classifier, enricher_system_prompt
from opalacoder.cli_commands import REPLState
from agenticblocks.blocks.llm.agent import AgentInput

async def test():
    store = ProjectStore()
    project = store.load("micalc") # Use the user's project
    
    chat_agent = make_chat_memgpt_agent(project.model)
    intent_classifier = make_intent_classifier(project.model)
    
    user_input = "Os botões da calculadora não funcionam"
    
    chat_agent.system_prompt = enricher_system_prompt()
    # Mock project context header
    enriched_obj = await chat_agent.run(AgentInput(prompt="Context...\n" + user_input))
    enriched_output = enriched_obj.response.strip() if enriched_obj.response else user_input
    
    print(f"ENRICHED OUTPUT:\n{enriched_output}\n")
    
    classifier_prompt = f"USER REQUEST: {user_input}\nENRICHED CONTEXT: {enriched_output}"
    print(f"CLASSIFIER PROMPT:\n{classifier_prompt}\n")
    
    intent_res = await intent_classifier.run(AgentInput(prompt=classifier_prompt))
    print(f"RAW INTENT CLASSIFIER OUTPUT: {repr(intent_res.response)}")

asyncio.run(test())
