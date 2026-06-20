# OmniMe `modelconfigs`: How It Works

## Overview

In OmniMe, `modelconfigs` work as a configuration management system for the language models you use.

They store refined model parameters and are part of the `assetstore` module, which is the local repository for reusable resources. The `assetstore` manages both:

* `skills`
* `modelconfigs`

In short, `modelconfigs` allow OmniMe to reuse, share, and automatically apply model-specific configuration files across projects.

---

## 1. Structure and Storage

`modelconfigs` are stored as global asset packages inside the OmniMe installation directory:

```text
omnime/assetstore/modelconfigs/
```

Each model configuration contains two files:

```text
<ID>.zip
<ID>.metadata
```

### `<ID>.zip`

A compressed package containing exactly one `.yaml` file.

This YAML file stores the model configuration parameters.

### `<ID>.metadata`

A plain text metadata file containing basic information such as:

* the asset identifier
* the asset type
* the description
* the model to which the configuration applies

Example metadata fields:

```yaml
id: <ID>
type: modelconfig
description: Configuration for a specific model
model: <provider>/<model-name>
```

---

## 2. Installation and Project Association

When you create or load a project using a specific model, for example:

```text
ollama/gpt-oss:latest
```

OmniMe attempts to apply the configuration associated with that model.

Project-specific model configurations are stored inside the hidden `.omnime` directory of the project, following this structure:

```text
<project-directory>/.omnime/modelsconfig/<provider>/<model_name>.yaml
```

The model identifier is adapted to be filesystem-safe.

For example:

```text
ollama/gpt-oss:latest
```

is transformed into:

```text
provider: ollama
file: gpt-oss__latest.yaml
```

So the local project configuration would be stored as:

```text
<project-directory>/.omnime/modelsconfig/ollama/gpt-oss__latest.yaml
```

---

## 3. Automatic Loading and Fallback Behavior

Whenever the OmniMe interface requests the configuration for a model through the following API route:

```text
/api/omnime/model-config
```

defined in:

```text
ide_server.py
```

the system follows this lookup order:

### Step 1: Look for the local project configuration

OmniMe first checks whether the exact configuration file exists inside:

```text
.omnime/modelsconfig/...
```

### Step 2: Try a fuzzy match

If the exact file is not found, OmniMe tries to find an approximate match among the local configuration files available for the same provider.

### Step 3: Search the Global AssetStore

If no local configuration is found, OmniMe searches the Global AssetStore.

If a compatible global `modelconfig` package exists, OmniMe automatically installs or copies that global configuration into the current project and then loads it.

This ensures that commonly used models can come preconfigured, so you do not need to manually adjust parameters for every new project.

---

## 4. Exporting a `modelconfig`

You can refine a model configuration through the OmniMe interface and export it.

The export route is:

```text
/api/omnime/export-modelconfig
```

This route receives the modified parameters, creates a temporary `.yaml` file, packages it into a `.zip`, generates the corresponding `.metadata` file, and saves everything to the destination folder you choose.

This allows you to:

* share model configurations with your team
* reuse tuned configurations across projects
* save a configuration as a future default
* version and distribute LLM parameter presets

---

## Summary

`modelconfigs` are OmniMe’s mechanism for ensuring portability, modularity, and reuse of LLM configurations through YAML files.

They allow model parameters to be packaged, shared, automatically discovered, and applied across different projects.

---

# Currently Supported `modelconfig` Parameters

OmniMe currently supports a strictly validated set of `modelconfig` parameters.

These parameters are divided into categories and cover standard text generation settings, special model modes, vision and attachment handling, and advanced agent/memory behavior.

Any field that is not included in the supported list, or whose value does not respect the defined limits, is automatically sanitized or discarded by the server in `ide_server.py` before being sent to the model.

---

## 1. Generation and Precision Parameters

### `temperature`

```yaml
temperature: 0.7
```

Type: `float`

Allowed range:

```text
0.0 to 2.0
```

Controls the randomness and creativity of the model output.

Lower values produce more deterministic responses, while higher values produce more varied and creative responses.

---

### `max_tokens`

```yaml
max_tokens: 2048
```

Type: `int`

Minimum value:

```text
1
```

Defines the maximum number of tokens generated in the response.

---

### `num_ctx`

```yaml
num_ctx: 8192
```

Type: `int`

Minimum value:

```text
1
```

Defines the size of the context window.

---

### `seed`

```yaml
seed: 42
```

Type: `int`

Minimum value:

```text
0
```

Sets the seed used to reproduce deterministic responses.

---

### `top_p`

```yaml
top_p: 0.9
```

Type: `float`

Allowed range:

```text
0.0 to 1.0
```

Controls nucleus sampling.

The model considers only the smallest set of tokens whose cumulative probability reaches `top_p`.

---

### `top_k`

```yaml
top_k: 40
```

Type: `int`

Minimum value:

```text
1
```

Restricts the sampling pool to the `K` most likely tokens.

---

### `min_p`

```yaml
min_p: 0.05
```

Type: `float`

Allowed range:

```text
0.0 to 1.0
```

Ignores tokens whose probability is below a `min_p` fraction of the most likely token.

---

### `frequency_penalty`

```yaml
frequency_penalty: 0.2
```

Type: `float`

Allowed range:

```text
-2.0 to 2.0
```

Applies a penalty based on token frequency.

This helps reduce repetitive output.

---

### `presence_penalty`

```yaml
presence_penalty: 0.2
```

Type: `float`

Allowed range:

```text
-2.0 to 2.0
```

Applies a penalty based on whether a token has already appeared in the generated text.

---

### `repetition_penalty`

```yaml
repetition_penalty: 1.1
```

Type: `float`

Minimum value:

```text
0.0
```

Provides another mechanism for controlling repeated text.

---

## 2. Special Modes and Reasoning Effort

### `think`

```yaml
think: true
```

Type: `bool`

When enabled, this may activate an explicit analytical or reasoning mode in compatible models, such as DeepSeek R1-style models.

---

### `stream`

```yaml
stream: true
```

Type: `bool`

Enables streaming responses, where the model output is sent in small chunks as it is generated.

---

### `reasoning_effort`

```yaml
reasoning_effort: medium
```

Type: `string`

Supported values:

```text
none
low
medium
high
xhigh
```

Optionally controls the model’s reasoning effort level.

---

## 3. Attachments and Vision

### `force_vision`

```yaml
force_vision: true
```

Type: `bool`

Forces the use of a vision-capable model when processing images.

---

### `pdf_truncate`

```yaml
pdf_truncate: true
```

Type: `bool`

Defines whether extracted PDF text should be truncated when it is too large.

---

### `pdf_truncate_pct`

```yaml
pdf_truncate_pct: 75
```

Type: `int`

Allowed range:

```text
1 to 100
```

Defines the percentage of the PDF content to preserve when truncation is applied.

---

## 4. Agent and Memory Settings

These settings are mainly related to agent behavior, long-running tasks, memory management, and MemGPT-style workflows.

---

### `max_heartbeats`

```yaml
max_heartbeats: 10
```

Type: `int`

Minimum value:

```text
1
```

Defines the maximum number of asynchronous agent turns, also called heartbeats.

---

### `max_context_tokens`

```yaml
max_context_tokens: 12000
```

Type: `int`

Minimum value:

```text
1
```

Defines the context limit used for memory management in continuous conversations.

---

### `eviction_threshold`

```yaml
eviction_threshold: 0.8
```

Type: `float`

Allowed range:

```text
0.0 to 1.0
```

Defines the threshold at which older memories begin to be evicted from the context.

This is commonly used in RAG or memory-based workflows.

---

### `memory_pressure_threshold`

```yaml
memory_pressure_threshold: 0.9
```

Type: `float`

Allowed range:

```text
0.0 to 1.0
```

Defines the critical context pressure point at which the agent needs to summarize or compress data.

---

### `max_iterations`

```yaml
max_iterations: 20
```

Type: `int`

Minimum value:

```text
1
```

Defines the maximum number of iterations the agent can use to solve a problem.

---

### `max_tool_calls`

```yaml
max_tool_calls: 15
```

Type: `int`

Minimum value:

```text
1
```

Defines the maximum number of tool calls allowed per turn.

---

### `loop_detection`

```yaml
loop_detection: true
```

Type: `bool`

Enables or disables loop detection.

This helps prevent infinite repetition of tool calls.

---

### `loop_detection_limit`

```yaml
loop_detection_limit: 3
```

Type: `int`

Minimum value:

```text
1
```

Defines the threshold used to decide whether the agent has entered a loop.

---

### `response_mode`

```yaml
response_mode: last
```

Type: `string`

Supported values:

```text
last
all
```

Defines how responses are collected.

Available modes:

* `last`: returns only the final response
* `all`: returns the complete interaction log

---

### `debug`

```yaml
debug: false
```

Type: `bool`

Enables local debug flags for model execution.

---

### `tool_role_workaround`

```yaml
tool_role_workaround: user
```

Type: `string`

Supported values:

```text
user
assistant
""
```

Forces function or tool responses to use another role.

This is useful for models that do not handle the `tool` role properly.

---

## Validation Behavior

The `modelconfig` system is strictly validated.

Any unsupported field is automatically sanitized or discarded before the configuration is sent to the model.

The same applies to supported fields whose values are outside the allowed limits.

For example, a configuration like this:

```yaml
temperature: 3.5
unknown_parameter: true
```

would be rejected, sanitized, or partially discarded because:

* `temperature` exceeds the allowed maximum of `2.0`
* `unknown_parameter` is not a supported field

---

## Example `modelconfig` YAML

```yaml
temperature: 0.7
max_tokens: 4096
num_ctx: 8192
seed: 42

top_p: 0.9
top_k: 40
min_p: 0.05

frequency_penalty: 0.2
presence_penalty: 0.1
repetition_penalty: 1.1

think: false
stream: true
reasoning_effort: medium

force_vision: false
pdf_truncate: true
pdf_truncate_pct: 75

max_heartbeats: 10
max_context_tokens: 12000
eviction_threshold: 0.8
memory_pressure_threshold: 0.9

max_iterations: 20
max_tool_calls: 15
loop_detection: true
loop_detection_limit: 3
response_mode: last
debug: false
tool_role_workaround: ""
```

---

## Final Notes

The `modelconfigs` feature provides a portable and reusable way to manage LLM behavior in OmniMe.

It allows each model to have its own validated YAML configuration, while also supporting project-level overrides, fuzzy matching, automatic fallback from the Global AssetStore, and exportable configuration packages.
