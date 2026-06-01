# BUGS TO FIX DETECTED ON LAST PUBLIC RELEASE (READ THE LAST SUBTOPIC)

## FROM CURRENT = 0.1.17 TO NEXT = 0.1.18

1. Terminal dont work, no obvious message in back terminal, but on IDE terminal we get the message "[OpalaCoder] Conexão com o terminal perdida. Reconectando...".

2. A janela de criação de projeto somente deveria permitir confirmar criação de projeto se o diretório especificado for válido.

3. New feature: install optional modules must be on IDE startup.

## FROM CURRENT = 0.1.18 TO NEXT = 0.1.19

1. Projeto não mostra nenhum erro quando o backend de modelos falha, por exemplo, tenta-se rodar um modelo que o ollama não tem instalado. 

2. Ao criar um novo arquivo, ficou congelado em carregando.

3. A aba de Problems nunca mostra nada errado, mesmo tendo.

4. Adicionar opção de renomear arquivo/diretório selecionado

5. Adicionar opção de limpar output e problems.

6. Abrir mais de uma aba no editor de arquivo (vários arquivos abertos ao mesmo tempo)

7. Verificar se o agente de comunicação com o backend é um LLMAgentBlock e, se for, como está as configurações de limite de chamada de ferramentas e de reflexão e outras.


Mensagens no chat não podem ser copiadas.