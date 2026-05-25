import asyncio
import litellm
import os
from dotenv import load_dotenv

# Load the user's API key
load_dotenv(os.path.expanduser("~/.opalacoder/.env"))
print(f"API Key present: {'GEMINI_API_KEY' in os.environ}")

async def test_model(model_name):
    print(f"\n--- Testing {model_name} ---")
    messages = [{"role": "user", "content": "Say 'hello'"}]
    try:
        res = await litellm.acompletion(model=model_name, messages=messages)
        print("SUCCESS! Response:")
        print(repr(res.choices[0].message.content))
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}")
        print(f"Error Message: {e}")

async def main():
    await test_model("gemini/gemini-3.5-flash")
    await test_model("gemini/gemini-1.5-flash")

asyncio.run(main())
