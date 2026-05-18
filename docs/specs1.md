Desenvolver um orquestrador baseado no orquestrador atual do projeto com as seguintes features:

1. Antes da fase de planejamento, o orquestrador procura por um profile no diretório de profiles.
2. Ao encontrar a profile, o planejamento é feito com base na descrição da profile.
3. Uma profile contém:
    3.1 Uma descrição, que o orquestrador usa para verificar se a profile se aplica.
    3.2 Uma descrição de tarefas indicando um grado de tarefas (tarefas no mesmo nível podem ser paralelizadas) que devem ser realizadas. Um descrição de grafo concisa deve ser usada. No grafo, as tarefas são representadas apenas por rotulos concecisos.
    3.3 Cada rótulo de tarefa funciona como um identificador, que será usado para descrever o que a tarefa faz.
    3.4 A descrição da tarefa pode conter um campo system_prompt que é usado para construir o agente que vai executar essa tarefa. Se o system_prompt não estiver presente, o orquestrador é chamado para gerar um system prompt adequado com base na descrição da tarefa  (indicar que é uma boa prática prover system_prompts para cada tarefa, poupando-se processamento pesado de inferência de LLM).
    3.5 A tarefa pode ter campos opcionais que definem como os parâmetros como temperature e top-k devem ser definidos, ou max_tokens.
4. Um sistema determinístico lê o arquivo de profile, que deve ser bem formado (um json?) e instancia um agente que executa essa tarefa de acordo com o grafo. No arquivo de configuração do sistema, pode-se definir a quantidade máxima de tarefas que podem rodar em paralelo. 


Se o orquestrador não encontrar um perfil específico, opalacoder continua com o orquestrador geral que já existe.

Crie um exemplo de profile de programador frontend_react_vite para ilustrar. Qual o formato de representação de perfil mais adequado?