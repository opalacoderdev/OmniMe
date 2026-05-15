tags: react, vite, npm, npx, node, javascript, js, ts, frontend
description: Regras e comandos obrigatórios para inicializar projetos React/Vite com npx de forma automatizada.
---
Se você precisar inicializar um projeto Vite usando `npx create-vite`, você DEVE usar OBRIGATORIAMENTE o comando 100% automatizado passando as flags `-y` e `--template react` (ou outro template se explicitamente pedido).
Exemplo: `npx -y create-vite@latest <nome_do_projeto> --template react`

ATENÇÃO CRÍTICA: NUNCA rode comandos que iniciam servidores de desenvolvimento ou travam o terminal (como `npm run dev` ou `npm start`), pois isso fará o script Python pendurar indefinidamente aguardando o processo terminar. Apenas construa o projeto e conclua a tarefa.
