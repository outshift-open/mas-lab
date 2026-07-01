<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Extensions lab (paper §5.3)

**Experiment** comparing memory **overlays** on the trip-planner **MAS**: vector
retrieval, Letta injection, baseline tools-only, and guardrail **overlay**.

Terms: [glossary.md](../../docs/glossary.md).

## Claim

Context sources are typed contracts. Adding memory is an **overlay** change, not
application code.

## Dependencies

Vector-memory scenarios use in-tree `SemanticMemoryPlugin` (no extra install).

**Letta scenarios** (`with-letta-memory`, `with-letta-factrecall`) require the
upstream [`letta`](https://pypi.org/project/letta/) package:

```bash
# workspace dev (recommended)
uv sync --group labs-full

# or install via mas-lab extra
pip install 'mas-lab[extensions]'
```

## Run

```bash
mas-lab benchmark run labs/extensions.lab/experiment.yaml --progress
```

Runs all **scenarios** × **dataset** items × `n_runs`, then the **embedded
pipeline**. Re-run to refresh figures from **trace cache**.

```bash
mas-lab benchmark run labs/extensions.lab/experiment.yaml --dry-run
```

## Output

`experiment.name`: `memory-extension-reproducibility`

`$XDG_DATA_HOME/mas/labs/memory-extension-reproducibility/results/`

```bash
mas-lab benchmark show last plots
```

## Layout

| Path | Role |
|------|------|
| `experiment.yaml` | **Scenarios**, **dataset**, **pipeline** |
| `overlays/` | **Overlay** manifests |
| `lib/steps/` | Custom **pipeline steps** |
| `RESULTS.md` | Interpretation |

## See also

- [labs-quickstart.md](../../lab/docs/labs-quickstart.md)
- [paper/index.md](../../docs/paper/index.md)
- [cli/observability.md](../../docs/cli/observability.md)
