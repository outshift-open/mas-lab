<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# LLM reasoning / thinking

**Schema:** `spec.models[].reasoning` on [`kind: Agent`](agent.md)
(`agent.schema.yaml`). **Protocol plugin:** OpenAI-compatible Chat Completions
(`OpenAILLMProvider`).

Reasoning models (OpenAI o-series / GPT-5, Gemini 2.5, DeepSeek-R1, gpt-oss,
Qwen3, …) spend **hidden thinking tokens** before the visible answer. Those
tokens must not land in working memory as if they were the assistant reply.
This page is the agent-facing surface for that.

---

## Spec vs contract vs catalog

**Spec** (`spec.models[]`) is the static overset: sampling, `reasoning`, and
`extra` (passthrough for vendor fields we have not named). **Contract**
(`LLMProvider.chat_completion`) is the per-call overset: `stream`,
`stream_options`, `tool_choice`, `extra_body`, `extra_headers`, `extra_query`.
**Catalog** ([llm-model-catalog.md](llm-model-catalog.md)) is per-model
`default` / `min` / `max` / `enum` / `supported` — same shape as context-window
tables. Unknown models are not deny-by-default; known models omit fields the
backend does not advertise (so Azure does not 400 on nested `reasoning`).

## What the APIs actually expose

These are the knobs vendors document. Named spec fields are the portable
overset; anything else goes in `spec.models[].extra` / `extra_body`.

| Knob | OpenAI Chat Completions | OpenAI Responses | LiteLLM / OpenRouter | Ollama | Anthropic | Gemini |
|------|-------------------------|------------------|----------------------|--------|-----------|--------|
| Effort / depth | `reasoning_effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` | `reasoning.effort` plus `reasoning.mode` (`standard` / `pro`, GPT-5.6) | `reasoning.effort` (alias `reasoning_effort`) | `think`: `true`/`false` or `low`/`medium`/`high` | adaptive thinking; effort mapped by LiteLLM | `thinkingConfig.thinkingBudget` |
| Thinking-token budget | billed inside `max_completion_tokens` (not a separate field) | `max_output_tokens` | `reasoning.max_tokens` | not a token budget | `thinking.budget_tokens` | `thinkingBudget` (0 = off) |
| Hide CoT from the message | hosted models already omit raw CoT | opaque `reasoning` items; optional `encrypted_content` | `reasoning.exclude: true` (OpenRouter convention) | `message.thinking` is separate; Chat Completions `exclude` is incomplete | thinking blocks | `includeThoughts` |
| Answer token cap | `max_completion_tokens` on reasoning models (`max_tokens` is rejected) | `max_output_tokens` | either | `num_predict` | `max_tokens` includes thinking | `maxOutputTokens` |

### What “not surfaced” used to mean

Earlier drafts left three vendor knobs off the spec because they were
Responses-only or unofficial on Chat Completions, and we had not live-tested
them:

| Field | Why it looked optional | Now |
|-------|------------------------|-----|
| `reasoning.mode` (`standard` / `pro`) | GPT-5.6 Responses; may 400 on `api.openai.com` Chat Completions | Named spec field. Catalog-gated. Sent as `reasoning.mode`. |
| `reasoning.include` (e.g. `reasoning.encrypted_content`) | Responses multi-turn encrypted CoT | Named spec field. Catalog-gated. Sent as top-level `include`. |
| `reasoning.think` | Ollama / vLLM / gpt-oss; LiteLLM’s OpenAI wrapper rejects top-level `think` | Named spec field. Catalog-gated. Ollama keeps `think`; native vLLM is flattened to `chat_template_kwargs.enable_thinking` in the JSON body. |

Live coverage: Outshift LiteLLM (`LITELLM_URL`) and GLS vLLM
(`OUTSHIFT_GLS_API_BASE`, default `https://vllm.outshift-gls.cisco.com/v1`).
Tests skip on missing credentials or DNS rather than fail CI.

Per-model defaults, maxima, and whether a field is supported:
[llm-model-catalog.md](llm-model-catalog.md).
Sampling overset (temperature, top_p, min_p, …): `llm-sampling.schema.yaml`.

---

## Spec surface (`spec.models[]`)

```yaml
models:
  - id: main
    model: gpt-5
    kind: openai
    temperature: 0.7
    max_tokens: 2000          # answer budget (see mapping below)
    reasoning:
      effort: low             # none | disable | minimal | low | medium | high | xhigh | max
      budget_tokens: 1024     # optional thinking-token cap
      exclude: true           # default; omit CoT from the assistant message
      mode: standard          # optional; Responses / LiteLLM
      think: true             # optional; Ollama / vLLM
      include:                # optional; Responses-style extras
        - reasoning.encrypted_content
```

`reasoning_effort: low` remains a deprecated alias for `reasoning.effort`.
If both are set, the nested object wins.

| Field | Default | Effect |
|-------|---------|--------|
| `reasoning.effort` | omitted | Sent as Chat Completions `reasoning_effort`. `none` / `disable` turn thinking off where the backend allows it (GPT-5.1+, Ollama via LiteLLM). gpt-oss **cannot** fully disable thinking — use a low effort and `exclude`. |
| `reasoning.budget_tokens` | omitted | Sent as `reasoning.max_tokens` (OpenRouter / Anthropic-style). Independent of `max_tokens`. `0` is “no thinking budget” on Gemini-via-LiteLLM. |
| `reasoning.exclude` | **true** | MAS strips `reasoning` / `reasoning_content` / `thinking` fields and `<think>` / `<thinking>` blocks from the assistant message (and from streamed `content` deltas). When the field is **present in the spec**, the plugin also sends `reasoning.exclude` for proxies that implement the OpenRouter convention. Official OpenAI Chat Completions may reject that extension, so it is **not** sent unless the spec set `exclude` explicitly. |
| `reasoning.mode` | omitted | Sent as `reasoning.mode` (`standard` / `pro`). Catalog-gated. |
| `reasoning.think` | omitted | Ollama: top-level `think`. Native vLLM: flattened `chat_template_kwargs.enable_thinking` (string values also set `thinking_level`). Catalog-gated. LiteLLM OpenAI-compatible HTTP often rejects both; the live think test skips with that error instead of retrying without think. |
| `reasoning.include` | omitted | Sent as `include` (e.g. `reasoning.encrypted_content`). |

### Token fields

When `effort` is set and is not `none`/`disable` **and** the catalog model is
not vLLM/Ollama, the OpenAI plugin sends `max_completion_tokens` (the o-series /
GPT-5 Chat Completions field) and omits `max_tokens`, which those models reject.
vLLM and Ollama keep `max_tokens`. The value is still `spec.models[].max_tokens`
— that is the **answer** budget. Hidden reasoning is billed inside it on OpenAI;
`budget_tokens` is the extra cap for backends that expose a separate thinking budget.
An explicit `max_completion_tokens` wins over this mapping; the request never
carries both fields, and carries neither when no limit is configured. Defaults,
ceilings, and `on_truncation`: [agent.md — Output-token limits](agent.md#output-token-limits).

`reasoning_effort` is sent as a top-level Chat Completions field. Nested
`reasoning` is only used for `budget_tokens` / `exclude` / `mode` — effort is
not duplicated inside it (strict OpenAI/Azure Chat Completions 400 on a nested
`reasoning` object that they do not expect).

---

## Why cache replay is unrelated

Offline CI replays a stored assistant message after sanitization. Configure
reasoning on the **live** protocol plugin, then record.

---

## Example

Keep thinking cheap and never show CoT:

```yaml
spec:
  models:
    - model: gpt-5-mini
      kind: openai
      max_tokens: 1500
      reasoning:
        effort: low
        exclude: true
```

Cap Gemini-style thinking tokens through an OpenAI-compatible proxy:

```yaml
spec:
  models:
    - model: gemini-2.5-pro
      kind: openai
      max_tokens: 2048
      reasoning:
        budget_tokens: 512
        exclude: true
```

### Overlays

Agent overlays may patch `spec.models[]` (deep-merge by `id`, then `model`,
then `main`). Connection fields (`api_base`, `api_key_env`) stay infra-only.

```yaml
kind: Overlay
spec:
  target:
    kind: Agent
  patch:
    models:
      - id: main
        reasoning:
          effort: low
          budget_tokens: 512
          exclude: true
          think: true
```

Deprecated `patch.llm.reasoning` still merges onto `spec.llm` when `models[]`
has no reasoning block.
