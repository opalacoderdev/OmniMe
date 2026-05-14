# Arquitetura do Sistema — ABCode

## Estratégia de Balanceamento de Modelos

O ABCode adota uma estratégia de uso em camadas para equilibrar qualidade e custo de tokens de API. O princípio central é a **divisão de responsabilidades entre dois tipos de modelo**:

- **Modelo maior (planejador):** responsável por raciocinar sobre o problema, decompô-lo e gerar um plano estruturado de execução.
- **Modelo menor (executor):** responsável por executar as etapas do plano de forma determinística e eficiente.

O modelo executor deve operar com **temperatura baixa ou igual a zero**, pois seu papel é maximizar o uso do próprio conhecimento parametrizado — não explorar variações criativas, mas tomar as melhores decisões disponíveis dado o contexto.

---

## A Natureza Markoviana dos LLMs e suas Implicações

### Formalização

LLMs são sistemas essencialmente **markovianos**: dado um modelo `f` com parâmetros fixos `b`, um estado de contexto `s` e um prompt `p`, a saída é determinada exclusivamente por esses três elementos:

```
f(s, p, b) → s'
```

O estado sucessor `s'` depende **somente** de `s`, `p` e `b` — e não de qualquer histórico anterior fora desse escopo. Como o agente não controla `s` diretamente e `b` é fixo (os pesos do modelo), **toda informação relevante precisa estar explícita em `p`**.

### Consequência Prática: o Papel do Contexto

Para que `f` produza comportamento racional, duas condições devem ser satisfeitas simultaneamente:

1. **Completude do contexto:** toda informação relevante para a tarefa deve estar presente em `p`.
2. **Direcionamento da atenção:** o mecanismo de atenção definido por `b` deve ser capaz de identificar e priorizar as partes relevantes de `p`.

Isso significa que **informações sobre o próprio ambiente de execução** — como restrições operacionais, limites de chamadas e estado da sessão — também são dados contextuais e devem ser explicitamente fornecidas ao modelo.

---

## Metadados como Informação de Contexto

### O Conceito de Metadado Operacional

Um **metadado operacional** é qualquer informação sobre as condições de execução do agente que não é parte do problema em si, mas que influencia as decisões que ele deve tomar.

### Exemplo Concreto: Limite de Rounds

Considere um fluxo em que o LLM deve:
1. Gerar um plano;
2. Confirmar o plano com o usuário via chamada de ferramenta;
3. Executar o plano após aprovação.

Se o ambiente impõe um **limite de 3 rounds de ação**, o modelo precisa dessa informação explicitamente no contexto para planejar sua sequência de ações de forma racional. Com esse metadado disponível, ele pode estruturar sua execução assim:

| Round | Ação |
|---|---|
| 1 | Gera o plano e solicita confirmação ao usuário |
| 2 | Processa a resposta e realiza ajuste ou segunda pergunta, se necessário |
| 3 | Executa o plano e entrega a resposta final |

Sem essa informação no contexto, o modelo não tem como saber que o round 3 é o último e pode alocar suas ações de forma subótima.

---

## Princípio Geral

> Todo comportamento esperado do agente que dependa de condições externas ao problema — limites de chamadas, permissões, estado da sessão, restrições de custo — deve ser **explicitamente codificado no prompt como metadado operacional**.

## Implicações
Um LLM, da forma como é treinado atualmente, não forma novas memórias à media que atua. Possui aminésia anterógrada desde que saem de fábrica.  Os próximos passos correspoondem a formalizar quais implicações esse fato tem para o uso da LLMs. A primeira implicação é  que LLMs se comportam essencialmente como sistemas markovianos. A segundo implicação é que, a engenharia de prompt é equivalente à engenharia de uma função de recompensa, no sentido de que dependem, para ter sucesso, de uma estato markoviano completo. Ou seja, o sistema deve ser completamente observável para que o prompt/função de recompensa sejam bem sucedidos.

Baseado nisso, estou criando ABCode, um agente de codificação que vai trabalhar para gerenciar de forma autônoma o uso de tokens, balanceando entre diferentes modelos no planejamento e execução de um plano. 