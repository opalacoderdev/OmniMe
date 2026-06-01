# Regras para Analises dadas Questões do Usuário
1. **Relevância**: As análises devem ser diretamente relevantes à questão do usuário, abordando os pontos específicos levantados e evitando informações desnecessárias.

2. Nunca levante hipóteses ou suposições sem base sólida. Se a questão do usuário for ambígua, peça esclarecimentos antes de fornecer uma análise. Realize testes para validar/excluir/confirmar hipóteses, e baseie suas análises nos resultados desses testes. Não invente testes fáceis de passar ou que não testem o que você diz que testam.

# Regras de Diagnóstico de Testes
1. **Cobertura de Código**: Assegure-se de que os testes cubram pelo menos 80% do código, incluindo casos de borda e cenários de falha.

2. **Isolamento**: Cada teste deve ser independente e não depender de outros testes ou do estado global. Use mocks e stubs para isolar as unidades de código.

2. **Repetibilidade**: Os testes devem produzir os mesmos resultados em execuções subsequentes, independentemente da ordem de execução ou do ambiente.

3. **Clareza**: Os testes devem ser claros e fáceis de entender. Use nomes descritivos para os testes e organize-os de maneira lógica.


# Regras de Organização de Testes
Nunca gere arquivos de teste soltos na raiz do projeto. Use o diretório `tests/` para organizar os testes por funcionalidade ou módulo.

# Regras de Nomenclatura de Testes
Siga a convenção de nomenclatura `test_<nome_da_funcionalidade>.py` para arquivos de teste. Dentro dos arquivos, nomeie as funções de teste com o prefixo `test_` seguido de uma descrição clara do que está sendo testado, por exemplo, `test_calculo_soma()`.
