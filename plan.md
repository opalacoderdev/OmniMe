**Panorama Geral para Implementação do Projeto OpalaCoderDE**

Abaixo está o plano técnico detalhado, dividido em fases, para continuar o desenvolvimento modular do projeto com base nas decisões anteriores (uso de  para frontend, , e integração local em Python).

---

1. **Configuração do Ambiente de Desenvolvimento**:
   Instalar dependências obrigatórias e configurar o ambiente Python (virtualenv) para garantir compatibilidade entre módulos.
   - Verificar versão do  (≥3.9) e instalar  para dependências.
   - Instalar  (API),  (integração IA), e bibliotecas para integração do Monaco ( ou  para embed).

2. **Integração do Monaco Editor**:
   Implementar o embed do Monaco Editor no ambiente  (usando  para renderização web em janela nativa).
   - Configurar linguagem padrão (Python/JS) e estilos do editor.
   - Conectar eventos do Monaco (salvar arquivo, seleção de código) à API interna via .

3. **Desenvolvimento do Módulo de Editor (Monaco + Terminal)**:
   Extender funcionalidades nativas do Monaco:
   - Adicionar suporte a autocompletar personalizado para palavras-chave de Python (integrado ao Monaco via extensão ou lógica personalizada).
   - Criar interface de terminal integrado (usando  para executar comandos Python no console).

4. **Desenvolvimento do Módulo de IA ()**:
   Implementar a camada de abstração para :
   - Criar um serviço interno () para envio/recebimento de prompts (com suporte a troca de modelos/serviços externos).
   - Gerenciar contexto do chat (histórico, arquivo aberto atual) em .

5. **API de Comunicação Interna ()**:
   Estabelecer rotas para:
   - Troca de mensagens entre o chat e o editor (ex: seleção de código para análise).
   - Executar comandos do chat no editor (ex: destacar linha, aplicar refatoração).

6. **Integração Frontend-Backend**:
   Conectar eventos do Monaco (ex: "arquivo salvo") à API para enviar conteúdo ao chat.
   - Atualizar a UI de chat com respostas recebidas via  (usando  para atualização dinâmica).
   - Validar comunicação bidirecional entre módulos (testes com casos de uso mínimos).

7. **Validação e Teste Básico**:
   Executar testes unitários e integração para:
   - Verificar fluxo de edição → chat → resposta → ação no editor.
   - Testar suporte a múltiplas abas e contextos isolados (histórico por arquivo).

---
**Notas Críticas**:
- **Modularidade**: Todos os módulos (, , ) devem ser inicializados independentemente para facilitar futuras trocas (ex: substituir  por outro serviço).
- **Embed Web**: Priorizar  para minimizar dívida técnica em relação ao  nativo.
- **Backend Local**: Todos os dados (histórico de chat, configurações) devem ser armazenados em arquivos JSON localmente para persistência.