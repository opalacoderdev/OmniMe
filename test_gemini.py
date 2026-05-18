import asyncio
import litellm
import os

async def main():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "{\"function\": \"test\"}", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]}
    ]
    try:
        res = await litellm.acompletion(
            model="gemini/gemini-3-flash-preview",
            messages=messages,
            api_key=os.environ.get("GEMINI_API_KEY")
        )
        print("Success:", res)
    except Exception as e:
        print("Error:", repr(e))

asyncio.run(main())
