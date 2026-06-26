<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS Library Samples

Reusable **artefacts** for tutorials and labs — not runnable experiments.

**Rule:** YAML samples live here, grouped by artefact type. Experiments belong only under `labs/*.lab/`.

## What belongs here

| Kind | Examples |
|------|----------|
| **apps** | `apps/trip-planner/`, `apps/qa-mas/` (mas, agents, local tools/skills) |
| **datasets** | `datasets/trip-planner/`, `datasets/generic/` |
| **tools** | `tools/calc.py`, `tools/*.tool.yaml` |
| **skills** | (under app trees or top-level when shared) |
| **overlays** | `overlays/cot.yaml`, `overlays/governance/` |
| **aliases** | `aliases/plugin-aliases.yaml` |

Generic pipelines, built-in steps, and shared artefacts belong in **`library-standard`** (or future lab-standard libraries), not here.

## What does *not* belong here

- **`experiment.yaml`** — only in `labs/<name>.lab/`
- Lab-specific pipeline definitions — colocate with the lab (`labs/.../pipeline-figure.yaml`, inline in experiment)
- One-off benchmark output paths or canvas exports

Labs **compose** library artefacts by registered id — not path traversal:

```yaml
mas:
  app: qa-agent
  configs_dir: ./overlays

dataset:
  name: qa-reasoning-queries-100
  locator: samples   # mas.runtime.manifest_libraries scheme
```

Install `mas-library-samples` (or `-e library-samples`) so the `samples` locator resolves via entry point.

Labs may also declare ``libraries: [samples]`` in ``lab-config.yaml`` to inject the library root at run time.

## Referencing from tutorials

Use **relative paths** from the tutorial bundle:

```bash
-o ../../../library-samples/overlays/governance/hitl-on-tool.yaml
```

Or copy the overlay into the tutorial `overlays/` folder for self-contained bundles.

Future: `@samples/overlays/governance/hitl-on-tool` resolved via workspace library registry.
