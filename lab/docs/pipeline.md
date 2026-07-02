<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Pipeline guide

A **pipeline** is a list of **pipeline steps** that run after **benchmark**
execution and write shared artifacts under `results/`.

Terms: [glossary.md](../../docs/glossary.md).

## Embedded vs standalone

**Embedded pipeline** — `application.post` inside `experiment.yaml`; runs automatically
when you `mas-lab benchmark run`:

```yaml
experiment:
  application:
    post:
      - name: extract-trace-stats
        type: extract_trace_stats
        config:
          output: "{output_dir}/results/trace_stats.csv"
```

**Standalone pipeline** — separate YAML; use when **runs** already exist:

```bash
mas-lab benchmark pipeline run labs/.../pipeline-figure.yaml -o $XDG_DATA_HOME/mas/labs/my-exp
```

Schema: [manifests/pipeline.md](../../docs/manifests/pipeline.md).

## Step catalog

[pipeline-steps.md](pipeline-steps.md).

## Step caching

Fingerprints live in `<output_dir>/.cache/`. Force one step:

```bash
mas-lab benchmark step restart <benchmark-id> <step-id>
```

See [benchmark CLI](../src/mas/lab/cli/commands/benchmark/).
