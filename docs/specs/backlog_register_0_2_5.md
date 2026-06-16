# BUGS TO FIX DETECTED ON LAST PUBLIC RELEASE (READ THE LAST SUBTOPIC)

## FROM CURRENT = 0.1.17 TO NEXT = 0.1.18

1. Terminal dont work, no obvious message in back terminal, but on IDE terminal we get the message "[OpalaCoder] Conexão com o terminal perdida. Reconectando...". ✅

2. A janela de criação de projeto somente deveria permitir confirmar criação de projeto se o diretório especificado for válido. ✅

3. New feature: install optional modules must be on IDE startup. ✅

## FROM CURRENT = 0.1.18 TO NEXT = 0.1.19

1. Projeto não mostra nenhum erro quando o backend de modelos falha, por exemplo, tenta-se rodar um modelo que o ollama não tem instalado. ✅

2. Ao criar um novo arquivo, ficou congelado em carregando. ✅

3. A aba de Problems nunca mostra nada errado, mesmo tendo. ✅

4. Adicionar opção de renomear arquivo/diretório selecionado. ✅

5. Adicionar opção de limpar output e problems. ✅

6. Abrir mais de uma aba no editor de arquivo (vários arquivos abertos ao mesmo tempo). ✅

7. Verificar se o agente de comunicação com o backend é um LLMAgentBlock e, se for, como está as configurações de limite de chamada de ferramentas e de reflexão e outras. ✅

## FROM CURRENT = 0.1.19 TO NEXT = 0.1.20

1. Implementar a visualização do pensamento do agente em uma aba thinking do painel inferior Implementar em uma aba separada thinking. ✅

2. Aumentar tamanho da fonte quando digitar ctrl+ no editor, ou diminuir quando digitar ctrl-.
3. Disponibilizar uma skill da ide que permite ao chat visualizar o conteúdo atual do editor e retornar o trecho selecionado. ✅

4. Colocar botão de interroper o agente. ✅

5. Descobrir porque o agente granite4:latest demora a responder. ✅

6. O erro ao criar um projeto em um diretório existente ou proibido deveria ser mostrado como mensagem na janela de criação de projeto e não no terminal (colocar mensagem correta, de acordo com exceção).
	6.1 Se diretório já existe e der erro de permissão, mostrar erro de permissão, se diretório não existe, criar diretório com nome do projeto. ✅

7. Colocar hint de completação de servidor ollama (já trazer preenchido com o valor que geralmente é). ✅

8. Criar uma janela de configuração de modelo com parâmetros mais usados que são aceitos no agenticblocks. E criar um comando set-model-param param-name value que permite qualquer parâmetro geralmente permitido pro litellm/ollama. Cuidado para implementar controle de verdade (valores adequados de parâmetro, por example). ✅

9. Permitir que mensagens no chat não podem ser copiadas. ✅

## FROM CURRENT = 0.2.3 TO NEXT = 0.2.4
1. Revisar código. ✅

2. Adicionar botões de maximizar e de minimizar o editor de texto (e outros paineis?). ✅

3. Adicionar o conceito de meta configurações de chat (configurações que somente são válidas naquele momento que se conversa com o agente - durante a vida de uma mensagem). Por enquanto, apenas os parâmetros max_tokens, system_prompt, temperature, top-k, top-p, min-p são permitidos. Exemplos:
	3.1 User: Implemente uma função que calcula a série de fourier. <param max_tokens=3>.
	3.2 Agent: ok ok
	3.3 User: Ora, ora, o que é você?  @system_prompt="seja irônico na resposta"@
	3.4 Agent: resposta irônica
	3.5 User:...
	3.6 Agent:...
	...

	Neste exemplo, em 3.1, o valor de max_tokens deve ser revertido depois que o agente der a resposta (a vida de uma meta instrução é só o do turno).
	Em 3.3, o system_prompt softre uma injeção, mas que dura somente enquanto o agente responde. Observe que, a partir de 3.3, max_tokens já volta para o seu valor padrão. E partir de 3.5, a injeção de system prompt perde o efeito (resetando-se o system prompt para sua versão original).
	Por baixo dos panos, primeiro identifica se a mensagem tem params, que são substituições válidas que começam com @, remove os parmas, faz a alteração temporária, executa a chamada, espera o modelo responder, desfaz a alteração temporária. ✅

4. Disponibilizar a ferramenta web_search para o agente. ✅

5. Terminal do windows 11. ✅

6. Menu contextual para copiar, cortar e colar no terminal. ✅

7. Adicionar mais opções de parâmetros na interface de configuração do projeto, como temperature,  top_p, top_k,  min_p,  presence_penalty, repetition_penalty. ✅

8. Histórico na entrada do chat. ✅

## FROM CURRENT = 0.2.4 TO NEXT = 0.3.0 (RELEASE FINAL DESSA ETAPA)

1. Revisar a Internacionalização. ✅ 

2. Implementar suporte a git. ✅

3. Prover ferramentas/funções de selecionar e pedir para o agente redefinir o que está selecionado. Ou para o agente detectar um erro em uma função ou trecho de código selecionado. Possíveis formas de se fazer isso:
	4.1 : o usuário seleciona o texto, e no menu contextual tem opções: refinar e corrigir se algo estiver selecionado. Também há a possibilidade do usuário selecionar algo ou deixar o cursor em alguma parte e executar CTRL+L e então abrir uma caixa em que o usuário pode pedir algo (o agente recebe o que foi selecionado, a linha inicial, a linha final e a posição do cursor. Uma interpretação é feita "se seleção vazia e linha inicial igual a linha final, focar na posição do cursor como o lugar onde posso começar a colocar algo.") ✅

4. Melhorar contraste dos themas (dark está razoável, o modo claro não está legal). ✅

5. Em refine e generate, é frágil a solução de mostrar os pensamentos do agente m thinking, dado que, tendo tido bloqueio das funções da IDE, muitas vezes (editor maximizado), não é possível olhar para essas subjanelas (thinking, output, etc). ✅

6. Na deleção de projeto, ter um check para escolher deletar pasta também.✅

# BUGS TO FIX DETECTED ON LAST PUBLIC RELEASE (READ THE LAST SUBTOPIC)

## FROM CURRENT = 0.1.17 TO NEXT = 0.1.18

1. Terminal dont work, no obvious message in back terminal, but on IDE terminal we get the message "[OpalaCoder] Conexão com o terminal perdida. Reconectando...". ✅

2. A janela de criação de projeto somente deveria permitir confirmar criação de projeto se o diretório especificado for válido. ✅

3. New feature: install optional modules must be on IDE startup. ✅

## FROM CURRENT = 0.1.18 TO NEXT = 0.1.19

1. Projeto não mostra nenhum erro quando o backend de modelos falha, por exemplo, tenta-se rodar um modelo que o ollama não tem instalado. ✅

2. Ao criar um novo arquivo, ficou congelado em carregando. ✅

3. A aba de Problems nunca mostra nada errado, mesmo tendo. ✅

4. Adicionar opção de renomear arquivo/diretório selecionado. ✅

5. Adicionar opção de limpar output e problems. ✅

6. Abrir mais de uma aba no editor de arquivo (vários arquivos abertos ao mesmo tempo). ✅

7. Verificar se o agente de comunicação com o backend é um LLMAgentBlock e, se for, como está as configurações de limite de chamada de ferramentas e de reflexão e outras. ✅

## FROM CURRENT = 0.1.19 TO NEXT = 0.1.20

1. Implementar a visualização do pensamento do agente em uma aba thinking do painel inferior Implementar em uma aba separada thinking. ✅

2. Aumentar tamanho da fonte quando digitar ctrl+ no editor, ou diminuir quando digitar ctrl-.
3. Disponibilizar uma skill da ide que permite ao chat visualizar o conteúdo atual do editor e retornar o trecho selecionado. ✅

4. Colocar botão de interroper o agente. ✅

5. Descobrir porque o agente granite4:latest demora a responder. ✅

6. O erro ao criar um projeto em um diretório existente ou proibido deveria ser mostrado como mensagem na janela de criação de projeto e não no terminal (colocar mensagem correta, de acordo com exceção).
	6.1 Se diretório já existe e der erro de permissão, mostrar erro de permissão, se diretório não existe, criar diretório com nome do projeto. ✅

7. Colocar hint de completação de servidor ollama (já trazer preenchido com o valor que geralmente é). ✅

8. Criar uma janela de configuração de modelo com parâmetros mais usados que são aceitos no agenticblocks. E criar um comando set-model-param param-name value que permite qualquer parâmetro geralmente permitido pro litellm/ollama. Cuidado para implementar controle de verdade (valores adequados de parâmetro, por example). ✅

9. Permitir que mensagens no chat não podem ser copiadas. ✅

## FROM CURRENT = 0.2.3 TO NEXT = 0.2.4
1. Revisar código. ✅

2. Adicionar botões de maximizar e de minimizar o editor de texto (e outros paineis?). ✅

3. Adicionar o conceito de meta configurações de chat (configurações que somente são válidas naquele momento que se conversa com o agente - durante a vida de uma mensagem). Por enquanto, apenas os parâmetros max_tokens, system_prompt, temperature, top-k, top-p, min-p são permitidos. Exemplos:
	3.1 User: Implemente uma função que calcula a série de fourier. <param max_tokens=3>.
	3.2 Agent: ok ok
	3.3 User: Ora, ora, o que é você?  @system_prompt="seja irônico na resposta"@
	3.4 Agent: resposta irônica
	3.5 User:...
	3.6 Agent:...
	...

	Neste exemplo, em 3.1, o valor de max_tokens deve ser revertido depois que o agente der a resposta (a vida de uma meta instrução é só o do turno).
	Em 3.3, o system_prompt softre uma injeção, mas que dura somente enquanto o agente responde. Observe que, a partir de 3.3, max_tokens já volta para o seu valor padrão. E partir de 3.5, a injeção de system prompt perde o efeito (resetando-se o system prompt para sua versão original).
	Por baixo dos panos, primeiro identifica se a mensagem tem params, que são substituições válidas que começam com @, remove os parmas, faz a alteração temporária, executa a chamada, espera o modelo responder, desfaz a alteração temporária. ✅

4. Disponibilizar a ferramenta web_search para o agente. ✅

5. Terminal do windows 11. ✅

6. Menu contextual para copiar, cortar e colar no terminal. ✅

7. Adicionar mais opções de parâmetros na interface de configuração do projeto, como temperature,  top_p, top_k,  min_p,  presence_penalty, repetition_penalty. ✅

8. Histórico na entrada do chat. ✅

## FROM CURRENT = 0.2.4 TO NEXT = 0.3.0 (RELEASE FINAL DESSA ETAPA)

1. Revisar a Internacionalização. ✅ 

2. Implementar suporte a git. ✅

3. Prover ferramentas/funções de selecionar e pedir para o agente redefinir o que está selecionado. Ou para o agente detectar um erro em uma função ou trecho de código selecionado. Possíveis formas de se fazer isso:
	4.1 : o usuário seleciona o texto, e no menu contextual tem opções: refinar e corrigir se algo estiver selecionado. Também há a possibilidade do usuário selecionar algo ou deixar o cursor em alguma parte e executar CTRL+L e então abrir uma caixa em que o usuário pode pedir algo (o agente recebe o que foi selecionado, a linha inicial, a linha final e a posição do cursor. Uma interpretação é feita "se seleção vazia e linha inicial igual a linha final, focar na posição do cursor como o lugar onde posso começar a colocar algo.") ✅

4. Melhorar contraste dos themas (dark está razoável, o modo claro não está legal). ✅

5. Em refine e generate, é frágil a solução de mostrar os pensamentos do agente m thinking, dado que, tendo tido bloqueio das funções da IDE, muitas vezes (editor maximizado), não é possível olhar para essas subjanelas (thinking, output, etc). ✅

6. Na deleção de projeto, ter um check para escolher deletar pasta também.✅

7. Inicializar configurações padrão do projeto com um modelo do ollama compatível com a máquina do usuário. ✅

8. Ao executar o software pela primeira vez, sugerir intalar o ollama (executar instalação via comando de instalação -- no window: irm https://ollama.com/install.ps1 | iex); no Linux: curl -fsSL https://ollama.com/install.sh | sh; no macosx:curl -fsSL https://ollama.com/install.sh | sh . se ainda não instalado (verificar complexidade e portabildiade dessa funcionalidade). Seria interessante instruir o usuário ou instalar por ele? ✅

9. Instalador autocontido para linux e windows. ✅

10. Path hint change according to the operation system. ✅

11. On project creation, set project name as the last folder name. ✅

12. Renderização de latex no chat. ✅

13. Send messages on chat while the agent is running (async messages on chat). 

14. PDF, media and websites on chat. Maybe with tools to summarize and take notes.

15. Export chat messages (pdf e markdown). 

DONE!
