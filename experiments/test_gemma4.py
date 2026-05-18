import asyncio
import json
import litellm
import time
import os
from pydantic import BaseModel, Field

# We will test exactly what happens when litellm talks to Gemma4 with the tool.
MODEL = "ollama/gemma4:latest"

async def run_rigorous_test():
    print(f"=== INICIANDO TESTE RIGOROSO COM {MODEL} ===")
    
    # 1. Definir a ferramenta (exatamente como no memgpt.py)
    tools = [{
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Sends a message to the user. Set request_heartbeat=true if you want to perform more actions (like searching memory) before giving control back to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "title": "Message"
                    },
                    "request_heartbeat": {
                        "type": "boolean",
                        "title": "Request Heartbeat",
                        "default": False
                    }
                },
                "required": ["message"]
            }
        }
    }]

    # 2. Definir o prompt do sistema
    sys_prompt = """You are running on an OS-like MemGPT architecture.
1. TOOL-ONLY INTERFACE: You MUST NEVER reply with plain text. Your only way to communicate with the user is by calling the `send_message` tool.
2. HEARTBEATS: Every tool you call consumes one 'heartbeat'."""

    # 3. Definir a mensagem do usuário (simulando a geração de um plano longo)
    user_msg = "Please execute the approved plan to create a complex Python IDE with PyQt6. This requires writing multiple files like main.py, editor.py, sidebar.py, terminal.py. Start your work by sending a detailed message about what you are going to do."

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_msg}
    ]

    print("--- CHAMANDO LITELLM ---")
    start = time.time()
    try:
        response = await litellm.acompletion(
            model=MODEL,
            messages=messages,
            tools=tools,
            temperature=1.0,
            max_tokens=8128,  # Valor configurado no YAML
            num_ctx=16384,
            drop_params=True # Importante: litellm costuma dropar params extras
        )
        elapsed = time.time() - start
        
        choice = response.choices[0]
        msg = choice.message
        
        print(f"\n[SUCESSO] Tempo de resposta: {elapsed:.2f}s")
        print(f"Token Usage: {response.usage}")
        print(f"Finish Reason: {choice.finish_reason}")
        print(f"Role: {msg.role}")
        
        print("\n--- CONTEÚDO (CONTENT) ---")
        if msg.content:
            print(msg.content)
            print(f"Tamanho do Content: {len(msg.content)} caracteres")
        else:
            print("VAZIO (None ou string vazia)")
            
        print("\n--- CHAMADAS DE FERRAMENTA (TOOL CALLS) ---")
        if msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"ID: {tc.id}")
                print(f"Função: {tc.function.name}")
                print(f"Argumentos Brutos (JSON):")
                print(tc.function.arguments)
        else:
            print("NENHUMA FERRAMENTA CHAMADA")

    except Exception as e:
        print(f"\n[ERRO LITELLM]: {str(e)}")

if __name__ == "__main__":
    asyncio.run(run_rigorous_test())
