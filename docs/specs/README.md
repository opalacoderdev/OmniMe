# OmniMe Specifications — Skills-Oriented Architecture

> **Status: IMPLEMENTED.** The skills-oriented redesign was implemented in the
> `refactor/skills-oriented-architecture` branch. These specs describe the
> architecture **as built**. The historical design markers —
> **(to implement)**, **(new)**, **(reuse)**, **(refactor)**, **⚠ to be approved** —
> refer to the previous approval process and have generally been resolved; where
> they still appear, they are origin notes, not pending work.

> **Divergências decididas durante a implementação** (empirically validated):
> - Script-driven skill execution is **pure claude.ai** (the LLM sub-agent calls
>   `run_command`), but the request travels via **`--request-file`** (not on the command
>   line) and the paths are **absolute** — see [06 §3](06-skills-e-plugins.md#3-invocação-a-tool-run_skill).
> - Memory engine = framework's `MemGPTAgentBlock`; requires **agenticblocks ≥ 0.8.37**
>   (text tool-call parser fix) — see [04 §1](04-memoria.md#1-memória-memgpt-clássica-do-chat-orquestrador).
> - `memgpt` role in `agents.yaml` (num_ctx 16384, max_heartbeats 20).
> - Execution resumption routed by MemGPT (there is no longer a `run_pipeline`).
> - `html-css-js` uses the `check_contracts.py` script (port of `html_css_js_tools.py`).

## Vision in one sentence

A **fixed MemGPT agent** converses with the user, maintains memory in the classic MemGPT
standard, and loads the **metadata (Level 1)** of active skills into its system prompt.
When the request matches a skill, it calls the **`run_skill`** tool, which
instantiates a **simple sub-agent** embedding the `SKILL.md` (Anthropic format,
*progressive disclosure* in 3 levels). Complex skills — like `implement-feature`
(the current Plan→Execute→Verify loop) — run their engine as a **Level 3 bash script**.
The sub-agent speaks to the user via a tool, and an
**interceptor** mirrors the dialogue back to the MemGPT's memory.

## Index

| Spec | Content |
|---|---|
| [01-arquitetura.md](01-arquitetura.md) | Principles, `omnime/` package (reuse/refactor/new), roles, and end-to-end flow. |
| [02-memgpt-orquestrador.md](02-memgpt-orquestrador.md) | Fixed MemGPT, `run_skill`, what is eliminated, execution resumption. |
| [03-skill-implement-feature.md](03-skill-implement-feature.md) | The skill that creates/fixes code: reused loop as Level 3 script, `intent`, checkpoints. |
| [04-memoria.md](04-memoria.md) | Classic MemGPT memory, core memory, archival (ChromaDB), vector index. |
| [05-vcs-sombra.md](05-vcs-sombra.md) | Shadow Git, VCS strategies, checkpoints per task, and `/undo`. |
| [06-skills-e-plugins.md](06-skills-e-plugins.md) | **Core:** `SKILL.md` format, 3 levels, `run_skill`, sub-agent, interceptor, security. |
| [07-configuracao.md](07-configuracao.md) | `agents.yaml`, `config.yaml`, removed roles, env vars, CLI flags. |
| [08-ide.md](08-ide.md) | **New:** IDE integration, stdin/stdout JSON protocol, asynchronous HTTP server, and REST APIs. |


## Decisions already incorporated

| Decision | Where |
|---|---|
| Skill = directory with `SKILL.md`; lean frontmatter (`name`/`description` + optional `model`); legacy fields discarded | [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai) |
| Sub-agent model selection via `model` field in `SKILL.md` | [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai), [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual) |
| Mandatory skills always loaded; `skills.yaml` filters the rest (controls token budget) | [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml) |
| Directories: project's `skills/` + `.omnime/skills` + `~/.omnime/skills` + built-ins | [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml) |
| Interceptor = wrapper on the `send_message` tool | [06 §4](06-skills-e-plugins.md#4-interceptador-de-diálogo) |
| `newfeat`/`bugfix` = single `intent` parameter in `implement-feature` | [06 §7](06-skills-e-plugins.md#7-skills-embutidas-previstas) |
| `command_hint` = instruction in the `chat-orchestrator` skill | [02 §3](02-memgpt-orquestrador.md#3-o-que-é-eliminado-do-desenho-atual) |
| By default (without `skills.yaml`), **only** mandatory skills are loaded; only `chat-orchestrator` is mandatory | [06 §5](06-skills-e-plugins.md#5-carregamento-de-skills-diretórios--skillsyaml) |
| `model` field in `SKILL.md` is **passed to the script** (`--model`) in script-driven skills | [06 §1](06-skills-e-plugins.md#1-formato-de-skill-padrão-anthropic--claudeai), [03 §2](03-skill-implement-feature.md#2-o-motor-loop-reusado) |
| Execution of skill scripts goes into `SENSITIVE_OPS` (approval in `edit` mode) | [06 §6](06-skills-e-plugins.md#6-segurança-skills-executam-bash-sem-sandbox) |
| Memory engine = framework's `MemGPTAgentBlock`; **remove** `omnime/memgpt.py` (Gemini out of scope) | [04 §1](04-memoria.md#1-memória-memgpt-clássica-do-chat-orquestrador) |

## Pending decisions — implementation details only

The **architecture** decisions are all resolved. There are three minor points remaining,
which can be defined during implementation (they do not block approval):

| Detail | Where |
|---|---|
| Checkpoint detection/resumption: in the skill script (recommended) or in the REPL | [02 §4](02-memgpt-orquestrador.md#4-retomada-de-execução-resume), [03 §5](03-skill-implement-feature.md#5-retomada-e-checkpoints) |
| Plan refinement: via intercepted tool (recommended) or direct I/O | [03 §4](03-skill-implement-feature.md#4-relação-com-a-fala-ao-usuário) |
| `complexity_inference_mode`: remove (recommended) — inherited inactive knob | [07 §2](07-configuracao.md#2-configyaml) |

## Conventions

- Code identifiers (`run_skill`, `edit_file`, `PlanOutput`, ...), file names
  and literal values are kept in English.
- `file:line` citations refer **only to existing code that will be
  reused** — new components don't have lines because they don't exist yet.
- Each spec declares its **status** at the top. Approve (or adjust) before requesting
  implementation.
