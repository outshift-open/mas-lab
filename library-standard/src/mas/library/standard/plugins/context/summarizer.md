<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# summarizer llm / drop — ContextManager sub-plugin

| Field | Value |
|-------|--------|
| **ID** | `llm` / `drop` (registry type `summarizer`) |
| **Kind** | summarizer (sub-plugin of `context_manager: summarising`) |
| **URN** | `mas.summarizer.llm`, `mas.summarizer.drop` |
| **Implementation** | `LlmSummarizer`, `DropSummarizer` in `mas.library.standard.plugins.context.summarizer` |
| **Manifest keys** | `spec.context_manager.params.summarizer` |
| **Overlay** | `pkg://mas.library.standard/overlays/cheap-summarizer.yaml` |
| **Example** | [examples/context/summarizer-override/](../../../../../../examples/context/summarizer-override/) (Agent; not a sample app) |

Not a top-level spec slot. `CMFactory` instantiates the binding and, for
`llm`, binds the agent engine. Compaction **triggers on the history token
budget** (`context_window − max_tokens`, or `summary_threshold`). The
system prompt is the payload of that call, not the trigger.

## Params (`llm` only)

| Attribute | Default | Meaning |
|-----------|---------|---------|
| `model` | agent primary model | `spec.models[].id` or LiteLLM string; resolved by `mas.runtime.spec.model_ref` |
| `instructions` | package constant (facts, decisions, identifiers; plain prose) | System prompt wrapping the JSON of older turns |

`drop` has no params: older turns are discarded, last `keep_turns` kept.

Context-manager knobs (not summarizer params): `keep_turns` (10),
`hysteresis_ratio` (0.2), `summary_threshold`, `trimmer`.

## Example (feature scenario)

[examples/context/summarizer-override/](../../../../../../examples/context/summarizer-override/)
pins `model` + `instructions` and a low `summary_threshold` so a short chat
compacts. `summarize_call.json` is the recorded payload. Index:
[examples/](../../../../../../examples/README.md).

```bash
mas-ctl validate library-standard/examples/context/summarizer-override/agent.yaml
mas-ctl chat library-standard/examples/context/summarizer-override/agent.yaml -v \
  -q "We fly to Lyon on 12 May."
```

Or overlay a cheaper model onto another agent (default instructions):

```bash
mas-ctl chat agent.yaml \
  -o pkg://mas.library.standard/overlays/cheap-summarizer.yaml
```

Authoritative thresholds, logs, and MCE judge:
[summarization.md](../../../../../../../docs/manifests/summarization.md).
