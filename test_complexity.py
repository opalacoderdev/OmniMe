import asyncio
from opalacoder.agents import make_complexity_evaluator
from agenticblocks.blocks.llm.agent import AgentInput
from dotenv import load_dotenv

load_dotenv()

async def test_complex():
    evaluator = make_complexity_evaluator("gemini/gemini-2.5-flash")
    res = await evaluator.run(AgentInput(prompt="Please refactor the entire system architecture, replace all synchronous code with asynchronous coroutines, integrate a completely new database backend, and write a comprehensive suite of integration tests for all 50 endpoints."))
    print("Response:", repr(res.response))

asyncio.run(test_complex())
