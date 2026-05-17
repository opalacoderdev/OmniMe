**Fase 0: Elicitação de Requisitos (Atualizado - Python Local)**

---
**Grupo 1 — Tecnologia e Dependências**
1. **Pilha tecnológica**: Python local (backend + frontend integrado via **`Monaco Editor`** — open-source e modular).
2. **Bibliotecas/Frameworks**:
   - Editor: **`Monaco Editor`** (Web-based, suporte nativo a *syntax highlighting*, autocompletar, multi-abas).
   - Chat: **`litellm`** (modular, com suporte a troca futura) + `FastAPI` (API interna para comunicação).
   - *Alternativa*: Evitar dependências externas complexas além do necessário.

---
**Grupo 2 — Requisitos Funcionais**
3. **Editor de código**:
   - *Obrigatório*: Syntax highlighting, autocompletar (palavras-chave + imports), multi-abas, split screen.
   - *Nice-to-have*: Dif lado a lado, integração com terminal Python (`subprocess`).
4. **Chat de agente**:
   - *Obrigatório*: Integração com `litellm` (modular), histórico de conversas.
   - *Nice-to-have*: Prompt personalizado, upload de arquivos (análise de código).
5. **Integração**:
   - Chat executa comandos no editor (ex: "refatorar função") e recebe código automaticamente ao salvar.

---
**Grupo 3 — Não Funcionais**
6. **Desempenho**: Otimizado para código médio (até 10KB), latência aceitável (<5s para respostas).
7. **Acessibilidade**: Teclado-navigável (padrões Web + Python GUI), contraste básico.
8. **Responsividade**: Desktop-only (janela ajustável).
9. **Ambiente**: Backend local (Python + `FastAPI` para API interna), frontend integrado via **`Monaco Editor`** (WebView ou embed).

---
**Resumo confirmado**:
- **Editor**: Módulo externo **`Monaco Editor`** (Web-based, modular) + integração com terminal.
- **Chat**: Agente modular via `litellm` + contexto de código.
- **Integração**: Commands bidirecionais (editor ↔ chat).
- **Tech**: Python puro, **`Monaco Editor`** (frontend), `litellm` (IA), `FastAPI` (comunicação).

---
**Próximos passos**:
1. **Fase 1: Estrutura do Projeto**
   - Diretórios:
     ```
     /OpalaCoderDE
     ├── core/
     │   ├── editor/
     │   │   └── monaco_integration.py  # Configuração do Monaco Editor
     │   ├── agent/
     │   │   ├── litellm_integration.py # Módulo litellm (modular)
     │   │   └── context_manager.py    # Histórico + código selecionado
     │   └── api/                      # FastAPI (comunicação)
     ├── ui/
     │   └── main_window.py            # tkinter (UI principal + WebView para Monaco)
     ├── tests/
     └── main.py
     ```

2. **Fase 2: Módulo Editor**
   - Implementar:
     - `monaco_integration.py` (configuração do Monaco Editor para Python/JS/etc.).
     - Integração com `subprocess` para terminal Python.

3. **Fase 3: Módulo Chat**
   - Configurar:
     - `litellm_integration.py` (abstração modular para `litellm`).
     - `context_manager.py` (gerenciar histórico + código selecionado).

4. **Fase 4: Integração**
   - Conectar UI aos módulos via `FastAPI` (API interna para comunicação).
   - Embed do Monaco Editor na janela `tkinter` (usar `WebView` ou `PyWebView`).