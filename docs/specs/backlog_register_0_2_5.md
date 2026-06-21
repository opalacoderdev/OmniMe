# BACKLOG 01 - ARCHIVED

## FROM CURRENT = 0.1.17 TO NEXT = 0.1.18

1. Terminal doesn't work, no obvious message in back terminal, but on IDE terminal we get the message "[OmniMe] Terminal connection lost. Reconnecting...". ✅

2. The project creation window should only allow confirming project creation if the specified directory is valid. ✅

3. New feature: install optional modules must be on IDE startup. ✅

## FROM CURRENT = 0.1.18 TO NEXT = 0.1.19

1. Project doesn't show any error when the models backend fails, for example, when trying to run a model that ollama doesn't have installed. ✅

2. When creating a new file, it froze on loading. ✅

3. The Problems tab never shows anything wrong, even when there are issues. ✅

4. Add an option to rename the selected file/directory. ✅

5. Add an option to clear output and problems. ✅

6. Open more than one tab in the file editor (multiple files open at the same time). ✅

7. Check if the agent communicating with the backend is an LLMAgentBlock and, if so, what are the settings for tool call limits, reflection, and others. ✅

## FROM CURRENT = 0.1.19 TO NEXT = 0.1.20

1. Implement the visualization of the agent's thoughts in a separate thinking tab in the bottom panel. ✅

2. Increase font size when typing ctrl+ in the editor, or decrease when typing ctrl-.
3. Provide an IDE skill that allows the chat to view the current content of the editor and return the selected excerpt. ✅

4. Add a button to interrupt the agent. ✅

5. Find out why the granite4:latest agent takes a long time to respond. ✅

6. The error when creating a project in an existing or forbidden directory should be shown as a message in the project creation window and not in the terminal (put the correct message, according to the exception).
	6.1 If the directory already exists and there's a permission error, show permission error, if the directory doesn't exist, create a directory with the project's name. ✅

7. Add a completion hint for the ollama server (already bring it filled with the value it usually is). ✅

8. Create a model configuration window with the most used parameters that are accepted in agenticblocks. And create a command set-model-param param-name value that allows any parameter generally allowed for litellm/ollama. Be careful to implement real control (appropriate parameter values, for example). ✅

9. Ensure that messages in the chat cannot be copied. ✅

## FROM CURRENT = 0.2.3 TO NEXT = 0.2.4
1. Review code. ✅

2. Add maximize and minimize buttons for the text editor (and other panels?). ✅

3. Add the concept of meta chat configurations (configurations that are only valid at that moment when chatting with the agent - during the life of a message). For now, only the parameters max_tokens, system_prompt, temperature, top-k, top-p, min-p are allowed. Examples:
	3.1 User: Implement a function that calculates the Fourier series. <param max_tokens=3>.
	3.2 Agent: ok ok
	3.3 User: Well, well, what are you?  @system_prompt="be ironic in your response"@
	3.4 Agent: ironic response
	3.5 User:...
	3.6 Agent:...
	...

	In this example, in 3.1, the value of max_tokens should be reverted after the agent gives the response (the life of a meta instruction is only for the turn).
	In 3.3, the system_prompt suffers an injection, but which lasts only while the agent responds. Note that, from 3.3, max_tokens already returns to its default value. And from 3.5, the system prompt injection loses its effect (resetting the system prompt to its original version).
	Behind the scenes, it first identifies if the message has params, which are valid substitutions that start with @, removes the params, makes the temporary change, executes the call, waits for the model to respond, and undoes the temporary change. ✅

4. Make the web_search tool available for the agent. ✅

5. Windows 11 terminal. ✅

6. Context menu to copy, cut and paste in the terminal. ✅

7. Add more parameter options in the project configuration interface, such as temperature, top_p, top_k, min_p, presence_penalty, repetition_penalty. ✅

8. History in chat input. ✅

## FROM CURRENT = 0.2.4 TO NEXT = 0.3.0 (FINAL RELEASE OF THIS STAGE)

1. Review Internationalization. ✅ 

2. Implement git support. ✅

3. Provide tools/functions to select and ask the agent to redefine what is selected. Or for the agent to detect an error in a selected function or code snippet. Possible ways to do this:
	4.1 : the user selects the text, and in the context menu there are options: refine and fix if something is selected. There is also the possibility for the user to select something or leave the cursor somewhere and press CTRL+L and then open a box where the user can ask for something (the agent receives what was selected, the start line, the end line and the cursor position. An interpretation is made "if selection is empty and start line equals end line, focus on the cursor position as the place where I can start putting something.") ✅

4. Improve themes contrast (dark is reasonable, light mode is not good). ✅

5. In refine and generate, the solution of showing the agent's thoughts in thinking is fragile, given that, having blocked the IDE functions, often (editor maximized), it is not possible to look at these subwindows (thinking, output, etc). ✅

6. On project deletion, have a check to choose to delete the folder as well.✅

# BUGS TO FIX DETECTED ON LAST PUBLIC RELEASE (READ THE LAST SUBTOPIC)

## FROM CURRENT = 0.1.17 TO NEXT = 0.1.18

1. Terminal doesn't work, no obvious message in back terminal, but on IDE terminal we get the message "[OmniMe] Terminal connection lost. Reconnecting...". ✅

2. The project creation window should only allow confirming project creation if the specified directory is valid. ✅

3. New feature: install optional modules must be on IDE startup. ✅

## FROM CURRENT = 0.1.18 TO NEXT = 0.1.19

1. Project doesn't show any error when the models backend fails, for example, when trying to run a model that ollama doesn't have installed. ✅

2. When creating a new file, it froze on loading. ✅

3. The Problems tab never shows anything wrong, even when there are issues. ✅

4. Add an option to rename the selected file/directory. ✅

5. Add an option to clear output and problems. ✅

6. Open more than one tab in the file editor (multiple files open at the same time). ✅

7. Check if the agent communicating with the backend is an LLMAgentBlock and, if so, what are the settings for tool call limits, reflection, and others. ✅

## FROM CURRENT = 0.1.19 TO NEXT = 0.1.20

1. Implement the visualization of the agent's thoughts in a separate thinking tab in the bottom panel. ✅

2. Increase font size when typing ctrl+ in the editor, or decrease when typing ctrl-.
3. Provide an IDE skill that allows the chat to view the current content of the editor and return the selected excerpt. ✅

4. Add a button to interrupt the agent. ✅

5. Find out why the granite4:latest agent takes a long time to respond. ✅

6. The error when creating a project in an existing or forbidden directory should be shown as a message in the project creation window and not in the terminal (put the correct message, according to the exception).
	6.1 If the directory already exists and there's a permission error, show permission error, if the directory doesn't exist, create a directory with the project's name. ✅

7. Add a completion hint for the ollama server (already bring it filled with the value it usually is). ✅

8. Create a model configuration window with the most used parameters that are accepted in agenticblocks. And create a command set-model-param param-name value that allows any parameter generally allowed for litellm/ollama. Be careful to implement real control (appropriate parameter values, for example). ✅

9. Ensure that messages in the chat cannot be copied. ✅

## FROM CURRENT = 0.2.3 TO NEXT = 0.2.4
1. Review code. ✅

2. Add maximize and minimize buttons for the text editor (and other panels?). ✅

3. Add the concept of meta chat configurations (configurations that are only valid at that moment when chatting with the agent - during the life of a message). For now, only the parameters max_tokens, system_prompt, temperature, top-k, top-p, min-p are allowed. Examples:
	3.1 User: Implement a function that calculates the Fourier series. <param max_tokens=3>.
	3.2 Agent: ok ok
	3.3 User: Well, well, what are you?  @system_prompt="be ironic in your response"@
	3.4 Agent: ironic response
	3.5 User:...
	3.6 Agent:...
	...

	In this example, in 3.1, the value of max_tokens should be reverted after the agent gives the response (the life of a meta instruction is only for the turn).
	In 3.3, the system_prompt suffers an injection, but which lasts only while the agent responds. Note that, from 3.3, max_tokens already returns to its default value. And from 3.5, the system prompt injection loses its effect (resetting the system prompt to its original version).
	Behind the scenes, it first identifies if the message has params, which are valid substitutions that start with @, removes the params, makes the temporary change, executes the call, waits for the model to respond, and undoes the temporary change. ✅

4. Make the web_search tool available for the agent. ✅

5. Windows 11 terminal. ✅

6. Context menu to copy, cut and paste in the terminal. ✅

7. Add more parameter options in the project configuration interface, such as temperature, top_p, top_k, min_p, presence_penalty, repetition_penalty. ✅

8. History in chat input. ✅

## FROM CURRENT = 0.2.4 TO NEXT = 0.3.0 (FINAL RELEASE OF THIS STAGE)

1. Review Internationalization. ✅ 

2. Implement git support. ✅

3. Provide tools/functions to select and ask the agent to redefine what is selected. Or for the agent to detect an error in a selected function or code snippet. Possible ways to do this:
	4.1 : the user selects the text, and in the context menu there are options: refine and fix if something is selected. There is also the possibility for the user to select something or leave the cursor somewhere and press CTRL+L and then open a box where the user can ask for something (the agent receives what was selected, the start line, the end line and the cursor position. An interpretation is made "if selection is empty and start line equals end line, focus on the cursor position as the place where I can start putting something.") ✅

4. Improve themes contrast (dark is reasonable, light mode is not good). ✅

5. In refine and generate, the solution of showing the agent's thoughts in thinking is fragile, given that, having blocked the IDE functions, often (editor maximized), it is not possible to look at these subwindows (thinking, output, etc). ✅

6. On project deletion, have a check to choose to delete the folder as well.✅

7. Initialize default project settings with an ollama model compatible with the user's machine. ✅

8. When running the software for the first time, suggest installing ollama (execute installation via installation command -- on windows: irm https://ollama.com/install.ps1 | iex; on Linux: curl -fsSL https://ollama.com/install.sh | sh; on macosx:curl -fsSL https://ollama.com/install.sh | sh . if not yet installed (check complexity and portability of this feature). Would it be interesting to instruct the user or install it for them? ✅

9. Self-contained installer for linux and windows. ✅

10. Path hint change according to the operating system. ✅

11. On project creation, set project name as the last folder name. ✅

12. Latex rendering in chat. ✅

13. PDF, media and websites on chat. Maybe with tools to summarize and take notes. ✅

14. Export chat messages (pdf and markdown). ✅ 

DONE!
