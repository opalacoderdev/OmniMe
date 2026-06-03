# Chat Meta-Parameters

Meta-parameters are per-turn configuration overrides embedded directly in a chat message. They take effect only for the duration of that single agent turn and are automatically reverted before the next message.

## Syntax

```
@key=value@
```

- String values must be quoted: `@system_prompt="be ironic"@`
- Numeric values are unquoted: `@max_tokens=512@` `@temperature=0.9@`
- Multiple params in the same message are supported: `@max_tokens=512@ @temperature=0.2@`
- Tokens are stripped from the message before it reaches the agent.

## Allowed Parameters

| Parameter      | Type   | Safe minimum | Description                                   |
|---------------|--------|-------------|-----------------------------------------------|
| `max_tokens`  | int    | 256         | Maximum tokens for the agent's LLM calls this turn |
| `temperature` | float  | 0.0         | Sampling temperature                          |
| `top_k`       | int    | 1           | Top-K sampling                                |
| `top_p`       | float  | 0.0         | Top-P (nucleus) sampling                      |
| `min_p`       | float  | 0.0         | Min-P sampling                                |
| `system_prompt` | str  | —           | Injects additional text as the system prompt for this turn only |

## Restrictions

### max_tokens minimum is 256

The `MemGPTAgentBlock` uses `max_tokens` for every internal LLM call — including tool-call heartbeats and response synthesis. Values below 256 cause the model to cut JSON tool calls mid-stream, producing empty or broken responses with no visible error.

Values below 256 are **automatically clamped to 256** with a warning in the server log. The user-specified value is never passed to the model.

### system_prompt is injected, not replaced

Setting `@system_prompt="..."@` **replaces** `agent.system_prompt` for that turn. The original is restored immediately after the agent responds. This means the injected prompt must be self-contained if it needs to include the original instructions.

### Parameters apply to all internal calls in a turn

For `chat_orchestrator` (MemGPT), a single user turn may trigger multiple LLM heartbeats. The override applies to every heartbeat in that turn, not just the final response call.

### Unknown keys are silently ignored

Any `@key=value@` token whose key is not in the allowed list is stripped from the message text but produces no override and no error.

## Examples

```
Implemente uma função de quicksort. @max_tokens=512@
```
Limits the agent's output budget for this turn to 512 tokens.

```
O que você acha da minha abordagem? @system_prompt="responda de forma muito crítica e direta"@
```
The agent responds with the injected system prompt; the original is restored on the next turn.

```
Resumo rápido. @max_tokens=300@ @temperature=0.2@
```
Multiple overrides in a single message.

## Implementation

| File | Role |
|------|------|
| `opalacoder/chat_meta_params.py` | Parser (`parse_meta_params`) and context manager (`apply_meta_params`) |
| `opalacoder/agent_stdin.py` | Integration point in `handle_run` — wraps `agent.run()` with `apply_meta_params` |
| `tests/test_chat_meta_params.py` | Unit tests for parser and restore logic |
