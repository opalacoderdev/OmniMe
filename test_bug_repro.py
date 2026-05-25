import asyncio
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.opalacoder/.env"))

from opalacoder.agents import make_intent_classifier
from agenticblocks.blocks.llm.agent import AgentInput

async def test():
    user_input = "os botões da calculadora não funcionam"
    enriched_output = """Há um bug na calculadora, nenhum botão funciona

[CONTEXT]
- **Erro de Sintaxe Ativo**: O arquivo `script.js` possui um erro de sintaxe crítico na linha 49 (`SyntaxError: Unexpected token '}'`), o que impede a execução de qualquer código JavaScript associado à calculadora.
- **Incompatibilidade de Contrato (HTML vs JS)**:
  - O botão `button#btn-clear` possui o atributo `data-action='clearDisplay'`, mas o JavaScript não trata a ação `'clearDisplay'`.
  - O botão `button#plus` possui o atributo `data-action='add'`, mas o JavaScript não trata a ação `'add'`.
- **Necessidade de Correção**: É necessário corrigir a sintaxe do arquivo `script.js` (fechando corretamente as chaves/instruções) e alinhar os manipuladores de eventos com os atributos `data-action` definidos no `index.html`."""

    classifier = make_intent_classifier("gemini/gemini-3.5-flash")
    
    classifier_prompt = f"USER REQUEST: {user_input}\nENRICHED CONTEXT: {enriched_output}"
    
    print("Calling make_intent_classifier.run()...")
    res = await classifier.run(AgentInput(prompt=classifier_prompt))
    print(f"RAW RES RESPONSE: {repr(res.response)}")

asyncio.run(test())
