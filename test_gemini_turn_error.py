import asyncio
import litellm
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.opalacoder/.env"))

async def test():
    # Sequence 1: Valid alternating
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "name": "test", "content": "result"}
    ]
    tools = [{"type": "function", "function": {"name": "test", "description": "test", "parameters": {"type": "object", "properties": {}}}}]
    
    try:
        print("Testing valid sequence...")
        res = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, tools=tools)
        print("Valid sequence passed.")
    except Exception as e:
        print(f"Valid sequence failed: {e}")

    # Sequence 2: assistant(text) then assistant(tool_call)
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
    ]
    try:
        print("\nTesting assistant(text) -> assistant(tool_call)...")
        res = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, tools=tools)
        print("Sequence 2 passed.")
    except Exception as e:
        print(f"Sequence 2 failed: {e}")

    # Sequence 3: user -> assistant(tool_call) -> NO tool response -> assistant(tool_call)
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "2", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
    ]
    try:
        print("\nTesting missing tool response...")
        res = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, tools=tools)
        print("Sequence 3 passed.")
    except Exception as e:
        print(f"Sequence 3 failed: {e}")

asyncio.run(test())
