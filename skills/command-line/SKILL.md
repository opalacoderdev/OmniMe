---
name: command-line
description: Executa operações de linha de comando para criar, inserir texto, remover arquivos e diretórios de forma segura dentro do workspace do projeto.
---

# Command Line Skill

Esta skill fornece ao sub-agente comandos python de linha de comando para manipular arquivos e diretórios de forma segura e restrita ao diretório do projeto.

## Comandos Disponíveis

Você deve executar o script `scripts/command_executor.py` usando a ferramenta `run_command`.
Os seguintes comandos e argumentos são suportados:

### 1. Criar Arquivo
Cria um novo arquivo com conteúdo opcional.
`python <command_executor.py_path> --project-path <project_path> create-file <relative_file_path> [--content "<content>"]`

### 2. Inserir Texto
Insere texto em um arquivo existente (ou adiciona ao final se a linha não for especificada).
`python <command_executor.py_path> --project-path <project_path> insert-text <relative_file_path> --content "<content>" [--line <line_number>]`

### 3. Remover Arquivo
Remove um arquivo existente. Apenas caminhos dentro do projeto são permitidos.
`python <command_executor.py_path> --project-path <project_path> remove-file <relative_file_path>`

### 4. Criar Diretório
Cria um novo diretório.
`python <command_executor.py_path> --project-path <project_path> create-dir <relative_directory_path>`

### 5. Remover Diretório
Remove um diretório existente de forma recursiva. Apenas caminhos dentro do projeto são permitidos.
`python <command_executor.py_path> --project-path <project_path> remove-dir <relative_directory_path>`
