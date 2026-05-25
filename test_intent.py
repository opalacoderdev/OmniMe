import asyncio
from opalacoder.agents import make_intent_classifier
from agenticblocks.blocks.llm.agent import AgentInput

async def test():
    classifier = make_intent_classifier("ollama/gemma4:latest")
    prompt = "USER REQUEST: Os botões da calculadora não funcionam\nENRICHED CONTEXT: Os botões da calculadora não funcionam"
    res = await classifier.run(AgentInput(prompt=prompt))
    print(f"RAW RES: {repr(res.response)}")

asyncio.run(test())
