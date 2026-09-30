<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# How to write manifests

Every attribute in a MAS Lab YAML file is one of three things: an **inline
object**, a **file path**, or a **catalog id**. A `LIBRARY:` prefix is valid
on any path or id — it is not specific to `app:`.

Kind-by-kind field lists live in this folder ([README](README.md)). This page
is the writing convention: how to point at those documents without
`../../apps/foo/mas.yaml`.

---

## 1. Inline, file, or id

```yaml
# Inline — the object is the manifest (or a fragment of one)
spec:
  agency:
    agents:
      - id: sre
        description: Orchestrator
        design_pattern: { type: react }

# File — separate YAML, referenced by path
      - id: telemetry
        ref: agents/telemetry.yaml          # relative to this mas.yaml
      - id: backend
        ref: example-library:apps/sre-triage/v1/agents/backend.yaml

# Id — catalog name, optionally versioned and library-qualified
experiment:
  application:
    app: example-library:sre-triage@v1        # id, not a path
  dataset:
    name: sre-triage-scenarios@v1
    locator: example-library
```

The dataset item is the run setup (`inputs.user` as a prompt string,
optional `hitl`, `memory_seeds`, `tool_fixtures`). File pointers use
`{ref: path}`. Ground truth is `expectations` on the same item.

| Form | When to use | Example |
|------|-------------|---------|
| **Inline** | Small fragments, one-off agent blocks, overlay `patch:` | `design_pattern: { type: cot }` |
| **File path** | A real document on disk | `./mas.yaml`, `samples:apps/trip-planner/mas.yaml` |
| **Catalog id** | A named app, dataset, or tool in a library | `example-library:sre-triage@v2`, `trip-planner` |

Do not encode version in the **name** (`sre-triage-v2`) or with a **slash**
(`sre-triage/v2`). Slash is a filesystem path. `@` is the version separator
(same as plugins: `react@v1`). App-specific datasets live under the app
version they evaluate: `apps/<app>/v<N>/datasets/<name>/`, with catalog id
`<dataset>@vN` and `spec.app: <app>@^vN`. Generic ones under library-root
`datasets/`.

---

## 2. `LIBRARY:` prefix

`name:path` always starts with a **library scheme** (`samples`, `example-library`,
`standard`, a lab-local `lib`, …). After the colon, write either:

- a **catalog id** — no slash: `example-library:sre-triage@v2`
- a **path inside a catalog object** — id, then slash:
  `example-library:sre-triage-incidents@v2/tool_fixtures/payment-async-timeout.yaml`
- a **library-relative path** — slash after a folder:
  `example-library:apps/sre-triage/v2/mas.yaml`

A slash after `name@version` is not a second copy of the file. It is a path
under that app or Dataset folder. Do not invent a sibling tree or a symlink
so overlays can `../` out of `mas.yaml`.

```yaml
# Prefer these
- app: example-library:sre-triage@v2
- manifest: samples:apps/trip-planner/mas.yaml
- ref: samples:tools/calc.tool.yaml
- incident_fixture: example-library:sre-triage-incidents@v2/tool_fixtures/payment-async-timeout.yaml

# Avoid climbing out of the lab
- manifest: ../../apps/sre-triage/mas.yaml      # don't
- ref: ../../../example-library/apps/sre-triage/v1/agents/sre.yaml
```

Unknown library names raise `LookupError`; they are never treated as relative
paths. Bare ids (`sre-triage@v2`, `trip-planner`) are looked up in the global
catalog before the filesystem.

`pkg://` remains a package-resource URI (`pkg://mas.library.samples/apps/...`).

---

## 3. Version grammar

Canonical id: **`[library:]name[@version]`**.

A spec **may** pin `@version`. Unpinned `sre-triage` is `@latest` (highest
`v*` folder), the same as `get_app` / `mas-ctl check`. Pin when you need a
specific major.

| Written | Resolves to |
|---------|-------------|
| `sre-triage@v2` | Folder `apps/sre-triage/v2/` |
| `sre-triage` / `sre-triage@latest` | Highest `v*` folder |
| `coding-agent-md` | Unversioned family — the name **is** the pin |
| `example-library:apps/sre-triage/v2` | Path under the library (directory) |
| `example-library:sre-triage-incidents@v2/tool_fixtures/foo.yaml` | File inside that Dataset folder |

On disk the version **is** the folder name: `apps/<name>/v<N>/`.
`library.yaml` may list the family (`sre-triage: apps/sre-triage`) or one
version (`sre-triage@v2: apps/sre-triage/v2`).

---

## 4. File names (what discovery actually looks for)

Do not invent a second suffix that fights these conventions. `mas.yaml` is
the app-root file; `*.mas.yaml` is an extra MAS **document**, not a second
app-root spelling.

| Kind | Conventional file | How it is found |
|------|-------------------|-----------------|
| Library | `library.yaml` | Folder with this file is a library root |
| Lab | `lab-config.yaml` | Folder `*.lab/` or a directory containing this file |
| Experiment | `experiment.yaml` | That name, or YAML under `experiments/` |
| MAS app root | **`mas.yaml`** (or `mas-bench.yaml`) | App directory scan; `get_app` / `app:` |
| Extra MAS document | `*.mas.yaml` | **Explicit** `library.yaml` `apps:` path or a `LIBRARY:…` file ref. Samples topologies use this (`parallel.mas.yaml`). Not scanned as an app root. |
| Agent | `agents/<id>.yaml`, `agents/<id>/agent.yaml`, or `agent.yaml` | Referenced from MAS `agency.agents[].ref` |
| Original persona tree | `agents/<id>/AGENT.md` | Non-mas-lab layout (e.g. `coding-agent-md`); directory still catalogued |
| Tool | `*.tool.yaml` | `tools/<name>.tool.yaml` or `tools/<name>/*.tool.yaml` |
| Overlay | `*.yaml` with `kind: Overlay` | Path / overlay id; often under `overlays/` |
| Dataset | `datasets/**/*.yaml` (`kind: Dataset`) or `apps/<app>/v*/datasets/<name>/dataset.yaml` | Catalog id or path. App-specific datasets declare `spec.app` for that app version. Generic datasets live under library-root `datasets/`. |
| Pipeline | `pipelines/*.yaml` (`kind: Pipeline` / `pipeline:`) | Path; `LIBRARY:` may omit `pipelines/` and `.yaml` |
| Plugin split-file | `plugins/*.plugins.yaml` | Optional; most plugins live inline in `library.yaml` |

Overlays do **not** require a `*.overlay.yaml` suffix. Some labs use that
name as documentation; discovery keys off `kind: Overlay` and the referring
path or overlay id.

---

## 5. Worked examples

### Experiment pin (preferred)

```yaml
# labs/example.lab/experiments/foo/experiment.yaml
experiment:
  name: foo
  application:
    app: example-library:sre-triage@v1
  dataset:
    name: sre-triage-scenarios@v1
    locator: example-library
  scenarios:
    - id: baseline
      overlays: []
```

### Experiment with a path (when you need a specific file)

```yaml
experiment:
  application:
    manifest: samples:apps/trip-planner/mas.yaml
    configs_dir: overlays
```

### MAS with mixed inline and files

```yaml
# apps/sre-triage/v2/mas.yaml
apiVersion: mas/v1
kind: MAS
metadata:
  name: sre-triage
spec:
  agency:
    agents:
      - id: sre
        ref: agents/sre.yaml          # file next to this manifest
      - id: risk_assessment
        ref: agents/risk_assessment.yaml
```

### Overlay file

```yaml
# overlays/no-tools.yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: no-tools
spec:
  target: { kind: Agent }
  patch:
    tools: { "$op": { clear: true } }
```

---

## See also

- [Manifest reference](README.md) — per-kind schemas
- [Labs vs libraries](../labs-and-libraries.md)
- [Library discovery](../library-discovery.md)
- [Experiment](experiment.md) · [MAS](mas.md) · [Agent](agent.md) · [Overlay](overlay.md) · [Tool](tool.md)
