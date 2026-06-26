<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Extend a lab

Add custom **pipeline steps**, **scenarios**, and **overlays** to a **lab** —
without standalone plotting scripts.

Start with [labs-quickstart.md](labs-quickstart.md). Terms: [glossary.md](../../docs/glossary.md).

## Custom pipeline step

1. Add `lib/steps/my_step.py` — implement `PipelineStep`, `register_step_type`.
2. Register the library in `lab-config.yaml`:

   ```yaml
   lab:
     libraries:
       - lib/
   ```

3. Add a step to `application.post` in `experiment.yaml`:

   ```yaml
   application:
     post:
       - name: my-step
         type: lib.steps.my_step:MyStep
         depends_on: [extract-trace-stats]
         config:
           output: "{output_dir}/results/my-figure.png"
   ```

Examples: [lifecycle-control.lab/lib/steps/](../../labs/lifecycle-control.lab/lib/steps/).

## Scenarios and overlays

- **Scenario** — new entry under `scenarios:` (`id`, `overlays`, optional `tags`)
- **Overlay** — YAML patch in `overlays/`; referenced by **scenario** or CLI `-o`
- **Dataset** — input items in `datasets/`

[overlays.md](../../docs/overlays.md) · [manifests/experiment.md](../../docs/manifests/experiment.md).

## Figures only via pipeline

Every figure is a **pipeline step** in `experiment.yaml`. Regenerate:

```bash
mas-lab benchmark run …
```

Reference PNGs: `figures/paper/`.

## Sub-experiments

Nested folders (e.g. `02-bit-exactness/`) are separate **labs** with their own
`experiment.yaml`.

## Evaluation

- Structural metrics from **`events.jsonl`**: `extract_trace_stats`, `extract_mealy_stats`
- Semantic metrics: `eval_mce` (judge model)

[library-eval/README.md](../../library-eval/README.md).

## Related

- [pipeline.md](pipeline.md)
- [reference/extensions.md](../../docs/reference/extensions.md)
