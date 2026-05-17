tags: criar, create, build, develop, implement, make, construir, desenvolver, implementar, programa, aplicativo, aplicação, sistema, projeto, app, software
description: Use ONLY when the user requests to BUILD, CREATE, or IMPLEMENT a new software project. When active, the agent must gather requirements via ask_human BEFORE any plan is generated.
scope: orchestrator
---
## General Developer — Pre-Planning Requirements Investigation

**THIS RULE IS MANDATORY AND MUST RUN BEFORE ANY PLAN IS CREATED.**

Whenever the user asks you to build, create, or implement any software, application, or feature,
you MUST NOT start generating a plan immediately.

Instead, you MUST first conduct a brief requirements elicitation interview using `ask_human`.

---

### Phase 0: Requirements Elicitation (Run BEFORE Panorama/Planning)

Call `ask_human` to ask the following questions. You may group them into one or two messages, but DO NOT skip any question.

**Question group 1 — Technology Stack:**
"Before I start planning, I need to understand your preferences:
1. Do you have a preferred technology stack? (e.g. plain HTML/CSS/JS, React, Vue, Next.js, Python Flask, FastAPI, Node.js, etc.) Or can I choose the most appropriate one?
2. Should I use any specific libraries or frameworks? Or do you prefer zero external dependencies?"

**Question group 2 — Functional Requirements:**
"Now, tell me about the features:
3. What are the CORE features this software must have? (List the must-haves)
4. Are there any features that would be nice to have but are not essential? (Nice-to-haves)"

**Question group 3 — Non-Functional Requirements:**
"Finally, some quality preferences:
5. Performance: Is speed a critical concern, or is correctness/simplicity more important?
6. Accessibility: Should it follow accessibility standards (WCAG / screen reader support)?
7. Responsiveness: Should it adapt to mobile screens, or is desktop-only acceptable?
8. Target environment: Where will this run? (Browser only, Node.js, desktop app, server, etc.)"

---

### After the Interview

Only after receiving the user's answers:
1. Summarize the confirmed requirements in a short bullet list.
2. Confirm with the user: "Based on your answers, here is what I will build: [summary]. Is this correct?"
3. Only after the user confirms, proceed to generate the plan (Panorama / Decomposition).

---

### Rules
- Never skip Phase 0. Even if the original request seems detailed, always ask at minimum questions 1 and 3.
- If the user says "you decide" or "whatever is best" for a question, that is a valid answer — record it as "agent's choice" and proceed.
- Keep the questions conversational and non-intimidating. Avoid technical jargon unless the user demonstrates technical knowledge.
- If the user has already provided some of this information in their request, acknowledge it and only ask about what is missing.
