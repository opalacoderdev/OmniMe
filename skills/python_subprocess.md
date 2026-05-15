tags: python, shell, bash, subprocess, script, comando
description: Proteções anti-travamento para comandos shell (subprocess) em scripts Python (devnull).
---
Sempre que precisar rodar comandos shell a partir do Python:
Use `import subprocess` e chame a função passando `stdin=subprocess.DEVNULL`:
`subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)`

A flag `stdin=subprocess.DEVNULL` é OBRIGATÓRIA. Ela impede travamentos infinitos caso qualquer comando tente ser interativo (pedir Y/N, senhas ou escolhas de menus). O script deve ser 100% automatizado.

Imprima o `stdout` e `stderr` de cada comando para que possamos logar e validar o resultado da execução.
