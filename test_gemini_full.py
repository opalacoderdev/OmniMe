import asyncio
import litellm
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.opalacoder/.env"))

async def test():
    system_prompt = """You are a strict intent router. Your job is to classify the USER REQUEST.
You will also receive RECENT CONTEXT (last 3 messages) to help you understand ambiguous requests (like "continue" or "fix it").

Classify the USER REQUEST into EXACTLY ONE of these categories: below.
Read each category carefully — they have clear, non-overlapping definitions.

- "command_hint": The user's ENTIRE message is exactly one of these CLI command words,
  optionally followed by arguments: clear, help, exit, quit, rename, list, load, delete,
  skills, lsskills, addskill, rmskill.
  The message contains NOTHING else — no question, no programming request, no context.
  Examples: "clear", "exit", "rename myproject", "addskill python".

- "greetings": The user is saying hello, goodbye, or exchanging casual pleasantries.
  No task is being requested.
  Examples: "hi", "thanks", "bye", "good morning".

- "question": The user is asking for an explanation, concept clarification, information
  about code, OR asking about the history/status of the project/conversation — WITHOUT
  requesting that anything be written, changed, or executed on disk.
  Examples: "what does async mean?", "how does this function work?",
  "what have we done so far?", "what did we change in this project?",
  "what is the current status?", "what changes were made?".

- "plan": The user wants a COMPLETELY NEW feature, project, or bug fix to be built, changed, or deleted on disk.
  Examples: "create a calculator", "fix the login bug", "add a dark mode".

- "resume": The user explicitly asks to continue, resume, finish, or keep going with the PREVIOUS or CURRENT plan that was interrupted or left halfway.
  Examples: "continue o que tinha feito antes", "resume the plan", "keep going", "finish it".

- "chat": A conversational message with no programming task implied — opinions, jokes,
  philosophical discussion, follow-up small talk.
  Examples: "that's interesting", "I don't like Python", "what do you think about AI?".

Respond with ONLY ONE WORD from the list: command_hint, greetings, question, plan, resume, chat.
No punctuation, no explanation."""

    user_prompt = """USER REQUEST: os botões da calculadora não funcionam
ENRICHED CONTEXT: Há um bug na calculadora, nenhum botão funciona

[CONTEXT]
- **Erro de Sintaxe Ativo**: O arquivo `script.js` possui um erro de sintaxe crítico na linha 49 (`SyntaxError: Unexpected token '}'`), o que impede a execução de qualquer código JavaScript associado à calculadora.
- **Incompatibilidade de Contrato (HTML vs JS)**:
  - O botão `button#btn-clear` possui o atributo `data-action='clearDisplay'`, mas o JavaScript não trata a ação `'clearDisplay'`.
  - O botão `button#plus` possui o atributo `data-action='add'`, mas o JavaScript não trata a ação `'add'`.
- **Necessidade de Correção**: É necessário corrigir a sintaxe do arquivo `script.js` (fechando corretamente as chaves/instruções) e alinhar os manipuladores de eventos com os atributos `data-action` definidos no `index.html`."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    print("Testing gemini-3.5-flash with NO kwargs...")
    res1 = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages)
    print(f"RES1: {repr(res1.choices[0].message.content)}")

    print("\nTesting gemini-3.5-flash with max_tokens=8128, temperature=0, num_ctx=2048...")
    res2 = await litellm.acompletion(model="gemini/gemini-3.5-flash", messages=messages, max_tokens=8128, temperature=0, num_ctx=2048)
    print(f"RES2: {repr(res2.choices[0].message.content)}")

asyncio.run(test())
