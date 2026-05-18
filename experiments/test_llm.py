import asyncio
import time
import litellm
from litellm import acompletion

# Desativa logs verbosos do litellm para o teste
litellm.suppress_debug_info = True

async def main():
    model = "ollama/gemma4:latest"
    print(f"Iniciando teste de velocidade e contexto com o modelo local: {model}")
    print("Isso provará se o travamento ocorre no OpalaCoder ou na geração local da LLM.\n")
    
    # Simulando um prompt gigante que se acumula após 11 heartbeats (ferramentas + respostas)
    large_context = "Você é um programador. " * 500  # Cerca de 1000 tokens
    
    messages = [
        {"role": "system", "content": "System: " + large_context},
        {"role": "user", "content": "Execute a ferramenta 'run_interactive_command' com o comando 'npm create vite@latest .'"}
    ]
    
    tools = [{
        "type": "function",
        "function": {
            "name": "run_interactive_command",
            "description": "Roda um comando iterativo no terminal",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    }]
    
    print("Enviando requisição (com contexto grande) para o Ollama local...")
    print("Cronometrando...")
    
    start = time.monotonic()
    
    try:
        response = await acompletion(
            model=model,
            messages=messages,
            tools=tools
        )
        elapsed = time.monotonic() - start
        
        print(f"\n[SUCESSO] O Ollama respondeu em {elapsed:.1f} segundos!")
        print("Resposta:")
        print(response.choices[0].message.content or response.choices[0].message.tool_calls)
        
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"\n[FALHA] O Ollama falhou/travou após {elapsed:.1f} segundos.")
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
