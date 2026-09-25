<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Example: summarizer override (`llm` plugin params)

Context-manager feature example. Not a sample app.

Default `context_manager: summarising` + `summarizer: llm` already uses the
**agent model** and a **package system prompt**. Compaction **fires on the
history token budget**, not on that prompt. This Agent pins two plugin
params:

- `params.model` — cheaper / dedicated summary LLM (`spec.models[].id`)
- `params.instructions` — replace the default system prompt

`summary_threshold: 80` is **only** so a short `mas-ctl chat` session
compacts. Production agents omit it; compile fills
`context_window − max_tokens` (126000 for the usual gpt-4o defaults).

`summarize_call.json` is the recorded chat-completions payload the `llm`
plugin would send (system prompt + JSON of older turns). It is not a runner.

| File | Role |
|------|------|
| `agent.yaml` | Runnable agent: `summarizer.params.model` + `instructions` |
| `summarize_call.json` | Recorded summary HTTP payload |

## Quickstart

From the repo root (workspace config / Tutorial 0 infra):

```bash
mas-ctl validate library-standard/examples/context/summarizer-override/agent.yaml
mas-ctl compile library-standard/examples/context/summarizer-override/agent.yaml --no-header
mas-ctl chat library-standard/examples/context/summarizer-override/agent.yaml -v \
  -q "We fly to Lyon on 12 May."
```

Repeat `-q` with follow-ups until INFO logs show `compacted` /
`summarizer llm: model=gpt-4o-mini`. With the example threshold of 80, two
or three short turns are enough.

To add a cheaper summarizer to some other agent without copying the CM
block, use the overlay:

```bash
mas-ctl chat other-agent.yaml \
  -o pkg://mas.library.standard/overlays/cheap-summarizer.yaml
```

The overlay sets `params.model: gpt-4o-mini` only (default instructions).

## What is overridable

| Field | Where | Default |
|-------|-------|---------|
| When it fires | `params.summary_threshold` / model window | `context_window − max_tokens` |
| Recency pin | `params.keep_turns` | `10` |
| Hysteresis | `params.hysteresis_ratio` | `0.2` |
| Plugin | `params.summarizer` | `llm` (`drop` = no LLM) |
| Summary LLM | `summarizer.params.model` | agent primary model |
| System prompt | `summarizer.params.instructions` | package constant (facts / decisions / identifiers, plain prose) |

There is **no** “please summarize now” user prompt. The CM compares an
estimated token count to the budget on every assemble.

## Docs

- [summarization.md](../../../../docs/manifests/summarization.md) — thresholds, model, prompt, logs, MCE judge
- Plugin card: [summarizer.md](../../../src/mas/library/standard/plugins/context/summarizer.md)
- Overlay index: [overlays/README.md](../../../src/mas/library/standard/overlays/README.md)
- Category: [context examples](../README.md)
