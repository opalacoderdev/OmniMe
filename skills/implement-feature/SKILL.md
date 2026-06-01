---
name: implement-feature
description: Cria, adiciona, altera ou corrige código em arquivos do projeto. Use quando o usuário pede para implementar uma funcionalidade nova ou consertar um bug.
model: alternative
---

# Implement Feature

Esta skill executa o loop completo **Planejar → Executar → Verificar** sobre os
arquivos do projeto. O motor é um script determinístico em Python.

## REGRA OBRIGATÓRIA

Para **qualquer** criação, alteração ou correção de código você **DEVE** executar o
script `run_workflow.py` chamando a ferramenta `run_command`. **NÃO** use
`write_file`, `edit_file` ou `replace_lines` diretamente nesta skill — esses
atalhos pulam o planejamento e a verificação e produzem resultados não confiáveis.
Sua única ação de execução deve ser **rodar o script** e, ao final, chamar
`send_message` com o resumo do que o script reportou.

## Como executar

Chame `run_command` com **exatamente** este formato (use o caminho ABSOLUTO do
script e o caminho ABSOLUTO do arquivo de request, ambos fornecidos no seu prompt):

```
python <CAMINHO-ABSOLUTO>/run_workflow.py --request-file <CAMINHO-DO-REQUEST> --intent <newfeat|bugfix>
```

Regras importantes:
- **NÃO** digite o texto do pedido no comando. O pedido já está salvo no arquivo
  indicado no seu prompto (`--request-file`). Isso evita erros de shell com
  parênteses e aspas.
- Use o `--intent` indicado no seu prompt.
- Seu diretório de trabalho é o do projeto, não o da skill — sempre caminhos
  absolutos.

- `--intent newfeat` → criar algo novo / adicionar funcionalidade.
- `--intent bugfix` → corrigir algo que existe e está quebrado (ativa o índice
  vetorial para localizar o defeito).
- `--model <valor>` (opcional) é repassado automaticamente pelo runner a partir do
  campo `model` desta SKILL.md; você não precisa informá-lo manualmente.

O script conduz planejamento (com aprovação do usuário), execução por workers com
auto-lint, e verificação em camadas, imprimindo o resultado final na saída padrão.
Relate ao usuário o que o script reportou.
