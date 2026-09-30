<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# LLM model catalog

**Schema:** `docs/schemas/runtime/llm-model-catalog.schema.yaml`
**Data:** `runtime/src/mas/runtime/spec/llm-model-catalog.yaml` (`metadata.version`)
**Loader:** `mas.runtime.engine.llm_model_catalog`

Per-model **context window**, **max output**, **defaults**, and **allowed
settings** — the same shape we want for a small reusable library. This repo
ships a **curated** YAML, not a vendor dump.

## Why not import LiteLLM wholesale

[LiteLLM `model_prices_and_context_window.json`](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json)
is the closest reusable community table (MIT). It is large, changes daily, and
is not a MAS schema. The catalog lists it under `spec.sources` with
`reusable: true` so a later `mas-llm-models` package can wrap that JSON behind
the same `ModelCatalog.get(name)` API.

Other pointers (not in-process libraries):

| Source | URL | Reuse |
|--------|-----|--------|
| OpenRouter models API | https://openrouter.ai/api/v1/models | live HTTP (`supported_parameters`) |
| models.dev | https://models.dev | aggregated community catalog |
| Hugging Face model cards | https://huggingface.co/models | cards / TGI |
| vLLM OpenAI server | https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html | `think` / `chat_template_kwargs` |
| Ollama API | https://github.com/ollama/ollama/blob/main/docs/api.md | `think` |
| Aider `MODEL_SETTINGS` | https://github.com/Aider-AI/aider/blob/main/aider/resources/model-settings.yml | Aider-specific YAML |
| Continue.dev | https://github.com/continuedev/continue | product configs |
| OpenClaw | historical MAS extract | **not in this tree** as a capability table — git history moved OpenClaw *plugins* (memory, telemetry), not a model list |

Each catalog `settings.<name>` entry may carry `supported`, `default`, `min`,
`max`, and `enum` (the allowed list). When the spec omits a field, catalog
`defaults` are applied. Numeric spec values are clamped to `min`/`max` when
the model is known. Reasoning knobs (`reasoning.*`, `think`, `include`) are
**deny-by-default** on known models: omitting the setting means unsupported.
Unknown models keep the spec as written. Do not use a `default` alias — it
collides with last-path-segment lookup.

## Shape

```yaml
apiVersion: mas/v1
kind: LlmModelCatalog
metadata:
  name: standard
  version: "2026.9.2"
spec:
  sources: [...]
  models:
    gpt-5:
      aliases: [openai/gpt-5]
      context_window: 400000
      max_output_tokens: 128000
      defaults:
        reasoning.effort: medium
      settings:
        reasoning.effort: {enum: [none, minimal, low, medium, high, xhigh]}
        reasoning.mode: {enum: [standard, pro]}
        think: {supported: false}
```

`ModelCatalog.get("openai/gpt-5")` resolves aliases. Unknown models are
permitted: the spec still sends what the user set; the catalog does not invent
a deny-by-default filter.

Bump `metadata.version` when curated numbers change.
