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

## FROM CURRENT = 0.1.19 TO NEXT = 0.1.20

1. Implementar a visualização do pensamento do agente em uma aba thinking do painel inferior Implementar em uma aba separada thinking
2. Aumentar tamanho da fonte quando digitar ctrl+ no editor, ou diminuir quando digitar ctrl-.
3. Disponibilizar uma skill da ide que permite ao chat visualizar o conteúdo atual do editor e retornar o trecho selecionado.
4. Colocar botão de interroper o agente.
5. Descobrir porque o agente granite4:latest demora a responder.
6. O erro ao criar um projeto em um diretório existente ou proibido deveria ser mostrado como mensagem na janela de criação de projeto e não no terminal (colocar mensagem correta, de acordo com exceção).
	6.1 Se diretório já existe e der erro de permissão, mostrar erro de permissão, se diretório não existe, criar diretório com nome do projeto.
7. Colocar hint de completação de servidor ollama (já trazer preenchido com o valor que geralmente é).
8. Criar uma janela de configuração de modelo com parâmetros mais usados que são aceitos no agenticblocks. E criar um comando set-model-param param-name value que permite qualquer parâmetro geralmente permitido pro litellm/ollama. Cuidado para implementar controle de verdade (valores adequados de parâmetro, por example).

9. Permitir que mensagens no chat não podem ser copiadas.