# 09 — Project Creation Interface Specification

This document details the fields and behaviors of the Project Creation/Registration dialog in the OpalaCoder IDE Web GUI.

## 1. Interface Layout & Fields

The registration dialog is styled using the dark VSCode theme, fitting within a modular modal panel. It contains the following configuration fields:

### 1.1 Project Name (Required)
* **Label**: Nome do Projeto *
* **Type**: Text
* **Placeholder**: `Ex: Meu Servidor Web`
* **Behavior**: Standard text input, validation prevents submit if empty. The backend slugifies this name (converting spaces to underscores and lowercase) to create the database project key.

### 1.2 Absolute Path (Required)
* **Label**: Caminho Absoluto *
* **Type**: Text
* **Placeholder**: `Ex: /home/gilzamir/projetos/meu-app`
* **Behavior**: Represents the absolute path to the project directory on the local filesystem. Automatically resolved and verified by the backend.

### 1.3 Description (Optional)
* **Label**: Descrição
* **Type**: Textarea (resizable: none, rows: 2)
* **Placeholder**: `Descritivo do projeto...`
* **Behavior**: Optional field used to give the agent semantic context about what the project does.

### 1.4 API Key (Optional)
* **Label**: Chave de API (Opcional)
* **Type**: Password input
* **Placeholder**: `Ex: sk-...`
* **Behavior**: Optional API token to authorize calls to LLMs (OpenAI, Gemini, etc.). If provided, the backend writes/appends `OPENAI_API_KEY=<api_key>` into the project's local `.env` file instead of storing it inside the SQLite database for security.

### 1.5 API Base URL (Optional)
* **Label**: URL Base da API (Opcional)
* **Type**: Text input
* **Placeholder**: `Ex: http://localhost:11434/v1`
* **Behavior**: Optional custom endpoint URL for OpenAI-compatible providers (like Ollama or local API endpoints). If provided, the backend writes `OPENAI_API_BASE=<api_base>` to the project's local `.env` file.
* **Hint**: Displays a detailed visual hint: *"Dica: Para usar o Ollama local com `ollama/ministral-3:14b`, informe a URL Base acima (ex: `http://localhost:11434/v1`) e digite/selecione o modelo correspondente."*

### 1.6 AI Model (Required)
* **Label**: Modelo de IA
* **Type**: Text input with a dropdown datalist
* **Placeholder**: `Selecione ou digite o modelo (ex: ollama/ministral-3:14b)`
* **Options in Datalist**:
  * `gemini/gemini-2.5-flash`
  * `gemini/gemini-2.5-pro`
  * `openai/gpt-4o`
  * `ollama/ministral-3:14b`
* **Behavior**: Allows selection or custom typing for the preferred primary model.

### 1.7 Execution Mode (Required)
* **Label**: Modo de Execução
* **Type**: Select dropdown
* **Options**:
  * `Auto (Completo)` (value: `auto`)
  * `Plan (Planejar)` (value: `plan`)
  * `Edit (Editar)` (value: `edit`)

## 2. API Endpoint Protocol

### `POST /api/opalacoder/create-project`
Creates the project in the store and registers standard project assets.

**Request Payload**:
```json
{
  "project_name": "My Web Server",
  "project_path": "/path/to/project",
  "description": "Short description",
  "model": "openai/gpt-4o",
  "mode": "auto",
  "api_key": "sk-...",
  "api_base": "http://localhost:11434/v1"
}
```