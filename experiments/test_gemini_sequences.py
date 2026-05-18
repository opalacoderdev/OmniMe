import asyncio
import litellm
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.opalacoder/.env"))

MODEL = "gemini/gemini-3-flash-preview"

async def test_sequence(name, messages):
    print(f"\n--- Testing: {name} ---")
    try:
        res = await litellm.acompletion(
            model=MODEL,
            messages=messages,
        )
        print(f"✅ SUCCESS")
        return True
async def run_all_tests():
    with open("test_results.txt", "w") as f:
        pass

    async def test_sequence(name, messages):
        with open("test_results.txt", "a") as f:
            f.write(f"\n--- Testing: {name} ---\n")
        try:
            res = await litellm.acompletion(model=MODEL, messages=messages)
            with open("test_results.txt", "a") as f:
                f.write("✅ SUCCESS\n")
            return True
        except Exception as e:
            with open("test_results.txt", "a") as f:
                err_str = str(e)
                if "BadRequestError" in err_str:
                    f.write(f"❌ BAD REQUEST: {err_str[:250]}...\n")
                else:
                    f.write(f"❌ OTHER ERROR: {err_str[:250]}...\n")
            return False

    tc = [{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]
    tc_resp = {"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": "file contents"}

    await test_sequence("Valid Tool Call -> Tool Response", [{"role": "user", "content": "read my file"}, {"role": "assistant", "tool_calls": tc}, tc_resp])
    await test_sequence("Assistant with both content and tool_calls", [{"role": "user", "content": "read my file"}, {"role": "assistant", "content": "I will read it", "tool_calls": tc}, tc_resp])
    await test_sequence("Tool Response followed by System Alert", [{"role": "user", "content": "read my file"}, {"role": "assistant", "tool_calls": tc}, tc_resp, {"role": "system", "content": "SYSTEM ALERT: Memory Pressure"}])
    await test_sequence("Tool Response followed by User Message", [{"role": "user", "content": "read my file"}, {"role": "assistant", "tool_calls": tc}, tc_resp, {"role": "user", "content": "SYSTEM EVENT: Checkpoint resumed"}])
    await test_sequence("Missing Tool Response", [{"role": "user", "content": "read my file"}, {"role": "assistant", "tool_calls": tc}])
    await test_sequence("First message is Assistant tool_call", [{"role": "assistant", "tool_calls": tc}, tc_resp])
    
if __name__ == "__main__":
    asyncio.run(run_all_tests())
