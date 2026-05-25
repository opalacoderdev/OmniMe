import asyncio
import litellm
import os

litellm.set_verbose = True

async def test():
    messages = [
        {"role": "system", "content": "You are a strict intent router. Respond with ONLY ONE WORD: plan. No punctuation."},
        {"role": "user", "content": "USER REQUEST: os botões da calculadora não funcionam\nENRICHED CONTEXT: Há um bug na calculadora, nenhum botão funciona"}
    ]
    
    print("Testing gemini-3.5-flash with NO kwargs...")
    try:
        res1 = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages)
        print(f"RES1: {repr(res1.choices[0].message.content)}")
    except Exception as e:
        print(f"ERR1: {e}")

    print("\nTesting gemini-3.5-flash with max_tokens=20...")
    try:
        res2 = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, max_tokens=20)
        print(f"RES2: {repr(res2.choices[0].message.content)}")
    except Exception as e:
        print(f"ERR2: {e}")

    print("\nTesting gemini-3.5-flash with temperature=0...")
    try:
        res3 = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, temperature=0)
        print(f"RES3: {repr(res3.choices[0].message.content)}")
    except Exception as e:
        print(f"ERR3: {e}")

    print("\nTesting gemini-3.5-flash with reasoning_effort='none'...")
    try:
        res4 = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, reasoning_effort="none")
        print(f"RES4: {repr(res4.choices[0].message.content)}")
    except Exception as e:
        print(f"ERR4: {e}")

asyncio.run(test())
