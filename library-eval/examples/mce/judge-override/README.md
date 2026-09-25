<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Example: MCE judge model (`eval_mce.config.model`)

Eval feature example. Not a sample app.

`eval_mce` already scored traces with an LLM-as-judge. The judge model is
`config.model`. Omit it and the step uses the **same model as the agent**
(experiment `metadata.model_name`, then workspace infra). This example
shows the two additive overrides:

- `experiment.evaluation.model` — default for every `eval_mce` that omitted `config.model`
- per-step `config.model` — still wins

Metric *prompts* live inside MCE (`mce_metrics_plugin`); this library does
not override them. Only the model id is configurable here.

| File | Role |
|------|------|
| `experiment.yaml` | Lab spec: evaluation.model + one strict step `config.model` |
| `mas.yaml` | Stub Agent so `applications.manifest` resolves |

## Quickstart

```bash
mas-ctl validate library-eval/examples/mce/judge-override/experiment.yaml
```

To run for real, point `applications` at a MAS that produced traces, then:

```bash
mas-lab benchmark run library-eval/examples/mce/judge-override/experiment.yaml --progress
```

INFO logs: `EvalMceStep … judge model=… source=experiment.evaluation.model`
(or `eval_mce.config.model` on the strict step).

## What is overridable

Existing `eval_mce` config (unchanged) plus **`model`**:

| Key | Default | Meaning |
|-----|---------|---------|
| `runs_dir` | pipeline output dir | Tree of `item*/r*/traces/events.jsonl` |
| `metrics` | all session MCE metrics | Subset to score |
| `overwrite` | `false` | Recompute `metrics.json` |
| `validate` | `true` | Schema-check artefacts |
| `max_workers` | `2` | Parallel judge calls |
| `fail_threshold` | `1.0` | Fraction of items that may fail |
| **`model`** | agent / infra | LLM-as-judge model |

## Docs

- [summarization.md § MCE judge](../../../docs/manifests/summarization.md#mce-judge-model)
- [experiment.md](../../../docs/manifests/experiment.md)
- [pipeline-steps.md](../../../lab/docs/pipeline-steps.md)
- Category: [MCE examples](../README.md)
