Ideia de Orquestrador Mais Eficiente para Modelos Locais

Ferramentas compostas: Em vez de fazer o modelo encadear 4 chamadas de ferramenta (encontrar arquivo → ler arquivo → editar arquivo → verificar), o OpalaCode dá a ele uma ferramenta que faz todas as 4. Modelos pequenos perdem coerência após 3+ chamadas sequenciais. Isso corta as falhas pela metade.

Loop de melhoria: Toda vez que o modelo escreve código, o OpalaCode compila/linta instantaneamente. Se falhar, retorna os erros automaticamente. O modelo não precisa ser inteligente o suficiente para acertar de primeira — ele só precisa corrigir os erros quando os vê.

Decompor na falha: Se o modelo falha na mesma coisa duas vezes, o OpalaCode para de tentar e em vez disso quebra o problema em partes menores. "Corrija este arquivo de 200 linhas" se torna "corrija apenas a linha 45."

Escalação: Se até a decomposição falhar e você tiver uma chave Claude/OpenAI configurada, ele escala automaticamente para o modelo maior apenas para aquela tarefa. Você permanece local 95% do tempo, na nuvem 5%.

Orçamento de tokens: Modelos pequenos têm contexto de 32k-256k. O OpalaCode nunca envia um arquivo inteiro. Ele resume, trunca e gerencia cada token, de modo que o modelo nunca vê a truncagem "..." no meio de um código importante.

Grafo de código: Em vez de procurar no seu código, o OpalaCode indexa seu código em um grafo de símbolos (funções, classes, quem-chama-o-quê). Quando você pergunta "como funciona a autenticação," ele percorre o grafo e retorna apenas o código relevante conectado — e não 15 pequenos trechos de arquivo aleatório.

Uma implementação dessas ideias, contudo em typescript, pode ser encontrada em (usar apenas como referência): https://github.com/Doorman11991/smallcode
