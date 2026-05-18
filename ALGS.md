# Algoritmos do OpalaCoder

Este documento descreve os principais algoritmos algorítmicos e fluxos de decisão adotados na arquitetura do OpalaCoder.

## 1. Algoritmo de Inferência Dupla de Complexidade e Orçamento Dinâmico

O OpalaCoder implementa um modelo inovador conhecido como **Two-Stage Predictive Budgeting** (Alocação de Orçamento Preditiva em Duas Fases) para garantir máxima eficiência financeira e resolutiva de agentes LLMs. O objetivo deste algoritmo é não desperdiçar tokens de modelos caros no planejamento inicial se a tarefa for trivial, mas não comprometer a execução caso o plano detalhado revele armadilhas arquiteturais.

A execução é controlada pela configuração `complexity_inference_mode` localizada no `agents.yaml`, operando nos modos `simple` ou `double`.

### Fluxo Lógico (Modo `double`)

O algoritmo segue as seguintes etapas procedurais:

1. **Primeira Fase: Inferência Heurística Pré-Plano (Estratégia 1)**
   - O usuário submete um prompt com seu pedido original.
   - O `make_complexity_evaluator` recebe este pedido cru e retorna um de dois labels de complexidade: `"default"` ou `"alternative"`.
   - Baseado neste label, o OpalaCoder escolhe o modelo base que gerará o "Panorama" (Phase 1) e conduzirá o Refinamento interativo (Phase 2).
   - *Propósito:* Garantir que a capacidade cognitiva inicial do planejador seja equivalente à complexidade presumida pelo usuário, poupando processamento excessivo em pedidos curtos.

2. **Loop de Refinamento de Plano**
   - O plano transita por ciclos interativos de aprovação humana. O resultado final desta etapa é o texto `approved_plan`.

3. **Segunda Fase: Avaliação JSON Pós-Plano (Estratégia 3)**
   - Ao invés de saltar direto para a execução (como agentes concorrentes fariam), o OpalaCoder intercepta o pipeline antes do orquestrador inicializar.
   - O `make_post_plan_evaluator` lê linha por linha o *`approved_plan`* finalizado pelo usuário. 
   - A saída exigida deste agente é um formato estrito em JSON:
     ```json
     {
       "model": "default | alternative",
       "estimated_steps": <inteiro>
     }
     ```
   - *Análise de Promoção de Execução (`model`)*: O algoritmo compara o modelo atual do orquestrador com a previsão JSON. Se o JSON concluir que a arquitetura traçada no plano é mais complexa do que aparentava no prompt (exigindo `"alternative"`) e o orquestrador estivesse setado como `"default"`, o algoritmo **promove (upgrade)** o orquestrador para o modelo alternativo *in-flight*, garantindo poder de raciocínio profundo para a etapa mais crítica.
   - *Cálculo do Orçamento (`max_heartbeats == "auto"`)*: Se o config de orquestração ditar heartbeats estáticos, nada muda. Porém, se for estipulado como `"auto"`, entra em vigor o cálculo de teto:
     ```python
     max_hb_config = min(estimated_steps * 3 + 5, 200)
     ```
     O número estimado de passos (read_file, write_file, run_command) extraído semanticamente pelo LLM é multiplicado por uma margem de segurança (3) mais um delta fixo (5), sempre limitado pelo limite lógico máximo (200), coibindo ciclos infinitos de alucinação.

4. **Execução**
   - O `AutonomousOrchestratorStrategy` herda o `model` reajustado e o `max_heartbeats` calculado organicamente e dispara as instâncias do MemGPT.

### Fallback Mode (Modo `simple`)
Se a configuração estiver em `simple` ou se a Extração JSON do *Post-Plan Evaluator* falhar por alucinação formativa:
- A promoção de modelo in-flight é ignorada.
- Se os heartbeats estiverem em `"auto"`, aplica-se um teto estático de contingência `max_hb_config = 50`.
