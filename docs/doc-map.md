<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Documentation map (contributors)

**This file is not published on GitHub Pages** (`exclude_docs` in `mkdocs.yml`).

## One source tree

All user documentation lives under **`docs/`**. GitHub Pages is **not** a separate
site — it is `mkdocs build` of this folder, driven by [`mkdocs.yml`](../mkdocs.yml)
at the repository root.

| Where | What |
|-------|------|
| [docs/index.md](index.md) | Site home (≈ align with root [README.md](../README.md)) |
| [mkdocs.yml](../mkdocs.yml) `nav:` | Left sidebar and top tabs on GitHub Pages |
| [outshift-open.github.io/mas-lab](https://outshift-open.github.io/mas-lab/) | Published output |

Local preview: `task docs-serve` → http://127.0.0.1:8000

When you add or rename a doc page, update **`mkdocs.yml` nav** and cross-links in
`README.md` / `docs/index.md` so the repo landing page and the site stay aligned.

---

## Site navigation (mirrors `mkdocs.yml`)

### MAS-Lab

- [MAS-Lab](index.md) — site home (quick links hub)
- [Overview](overview.md) — problem, developers, enterprises, researchers

### User guide

- [User guide](user-guide.md)
- [User configuration](user-config.md)
- [Package map](libraries.md)
- [Observability / run logs](cli/observability.md)
- **[Web UI](ui/index.md)**
- [Terminal UI (TUI)](ctl/tui.md)
- [Glossary](glossary.md)

### Tutorials

- [Tutorials index](tutorials/index.md)
- [0 — Environment setup](tutorials/00-environment-setup/README.md)
- [1 — Build an agent](tutorials/01-building-an-agent/README.md)
- [2 — Orchestrate your MAS](tutorials/02-creating-a-mas/README.md)
- [3 — Run an experiment](tutorials/03-experiments-and-analysis/README.md)

### References

- [References index](references/index.md)
- Specifications → `manifests/*.md`, [schemas](references/schemas.md)
- Runtime → [manifests/runtime.md](manifests/runtime.md), [runtime docs](references/runtime.md)
- Lab & benchmarks → experiment/dataset/pipeline manifests, [lab bench](references/lab.md)

### Paper

- [Paper labs & reproducibility](paper/index.md)

### Blog

- [All posts](blog/index.md) · categories **Updates** / **Releases**

---

## Outside `docs/` (linked, not on Pages)

| Path | Audience |
|------|----------|
| [`docker/README.md`](../docker/README.md) | Docker compose, mounts, env |
| [`ui/README.md`](../ui/README.md) | UI package development (Yarn, Vite) |
| [`runtime/docs/`](../runtime/docs/) | Runtime contributor docs |
| Internal extensions (evolution, KG, rust) | Not published in OSS — separate internal repository |

---

## Contributing

[CONTRIBUTING.md](https://github.com/outshift-open/mas-lab/blob/main/CONTRIBUTING.md) at the repository root.
