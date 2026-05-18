import asyncio
import litellm
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.opalacoder/.env"))
MODEL = "gemini/gemini-3-flash-preview"

async def test_tool_then_system():
    tc = [{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]
    tc_resp = {"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": "file contents"}
    messages = [
        {"role": "user", "content": "read my file"},
        {"role": "assistant", "tool_calls": tc},
        tc_resp,
        {"role": "system", "content": "SYSTEM ALERT: Memory Pressure"}
    ]
    
    try:
        res = await litellm.acompletion(model=MODEL, messages=messages)
        with open("direct_test_result.txt", "w") as f:
            f.write("SUCCESS")
    except Exception as e:
        with open("direct_test_result.txt", "w") as f:
            f.write(f"ERROR: {str(e)}")

asyncio.run(test_tool_then_system())
