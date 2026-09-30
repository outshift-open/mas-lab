# Library discovery

> Examples use a synthetic `example-library` fixture to demonstrate discovery
> syntax. It is not an installed MAS-Lab package.
<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Library discovery (developers)

User-facing model: [labs-and-libraries.md](labs-and-libraries.md). This page
is the contract ctl, runtime, and lab share.

Shared helpers live in `runtime/src/mas/library_roots.py`:

- `iter_named_library_roots(*anchors)` — ordered `(name, root)` pairs
- `resolve_named_library_root(name, *anchors)` — root or `None`

A **manifest library** is a folder with `library.yaml` at its root.
`name:path` always uses a library name. Unknown names raise `LookupError`
(they are never treated as a filesystem path). The lab validator fails closed
on unknown library names.

Do not put `library.yaml` on the lab root. `mas-ctl` must not depend on
`mas-library-samples`.

---

## How a library becomes visible

Two doors, one outcome: a folder with `library.yaml` is found, and that
manifest fills the catalog (apps, datasets, tools).

1. **Install** — `uv pip install -e example-library` registers scheme
   `example-library` on the `mas.runtime.manifest_libraries` entry point.
2. **Search paths** — a list of folders to look in. Each entry is a library
   root, or a parent of sibling library folders. The name is the found
   directory stem. Do not invent aliases (`ioc` for `example-library`).

The search lists already exist and use the same scan
(`iter_libraries_in_search_path`):

| Where | Field |
| --- | --- |
| Lab | `lab-config.yaml` → `lab.libraries` |
| Workspace | `config.yaml` → `manifest_libraries` |
| Environment | `MAS_LIBRARY_PATHS` (`os.pathsep`) |

```yaml
lab:
  libraries:
    - lib/
    - ../../../example-library

manifest_libraries:
  - .                     # this workspace: example-library/, library-kg/, …
  - ../other-libraries
```

A listed directory **without** `library.yaml` is still put on Python
`sys.path` (lab-local code). Immediate children of the lab root that contain
`library.yaml` are picked up too.

## Search order

First-seen name wins. Lab-local wins over workspace and installed libraries
of the same name.

1. Lab-local search paths (`lab.libraries` + lab-root children)
2. Workspace search paths (`manifest_libraries`)
3. Installed libraries (entry points)
4. `MAS_LIBRARY_PATHS`
5. Ancestor walk from anchors/cwd for `library.yaml`, stopping at `.git`
   and `.lab`. A `library.yaml` on the lab root is not dual-registered.

`.git` is a walk boundary, not a search root.

---

## `library.yaml` contract

Schema: [`docs/schemas/library.schema.yaml`](schemas/library.schema.yaml).
Kind `Library`, `apiVersion: mas/v1`, flat (no `metadata:` / `spec:`).

| Field | Role |
| --- | --- |
| `name` | Package-style identity (`mas-library-samples`, `lifecycle-control-lib`) |
| `schemes` | Optional extra identifiers. Prefer one name: the directory stem and the install entry point. Do not add aliases. |
| `apps` / `datasets` / `tools` | Catalogs for `library:app`, `name:path`, and `app:` lookup. App keys are `name` or `name@version`; a value may be a family dir (`apps/sre-triage`) or one version dir. |
| `types` / `plugins` | Plugin manifest payload (same shape as `*.plugins.yaml`) |
| `plugin_manifests` | Extra plugin YAML files, if you split them |

`library.yaml` is the plugin manifest when it declares `types:` / `plugins:`.
See [plugin-registry-manifests.md](../runtime/docs/plugin-registry-manifests.md).

In-repo labs that list a local dir ship `library.yaml` there so the dir is a
real library. Pipeline YAML may still load steps by Python path
(`lib.steps.figure_call_counts:FigureCallCountsStep`); the manifest catalogs
them so root discovery and `name:path` see the library.

---

## Scheme vs package name

The prefix in `samples:tools/calc.tool.yaml` is the **library name**
(`samples`), not the distribution name (`mas-library-samples`). Installed
names in this repo: `samples`, `standard`, `lab`, `skills`, `ioa`.

Lab-local listed basename `lib/` → scheme `lib` (does not collide with those
installed names).

---

## Versioned catalog ids

Same separator as plugins (`react@v1`): **`[library:]name[@version]`**.

- On disk: `apps/<name>/v<N>/` — the folder name is the version tag.
- Bare `name` is `@latest` (highest `v*` folder) for lookup
  (`get_app`, `mas-ctl check`, and experiment `app:` / `dataset.name`).
  Pin `@version` when you need a specific major.
- After `LIBRARY:`, no slash means an id (`example-library:sre-triage@v2`).
  A slash after `name@version` is a path **inside** that catalog object
  (`example-library:sre-triage-incidents@v2/tool_fixtures/routing-policy-rollback.yaml`).
  A slash after a folder is a path from the library root
  (`example-library:apps/sre-triage/v1/datasets/scenarios/tool_fixtures/routing-policy-rollback.yaml`).
- `sre-triage-v2` and `sre-triage/v2` are **not** id aliases.

**Datasets** use the same `name@version` grammar. App-specific datasets live
at `apps/<app>/v<N>/datasets/<dataset>/dataset.yaml` (same version folder as
the app) and declare `spec.app` (`sre-triage@^v1`). Generic datasets live
under library-root `datasets/`.

User-facing writing rules: [writing-manifests.md](manifests/writing-manifests.md).

---

## See also

- [How to write manifests](manifests/writing-manifests.md)
- [Labs vs libraries](labs-and-libraries.md)
- [User configuration](user-config.md)
- [lab-config schema](schemas/lab/lab-config.schema.yaml)
- [workspace config schema](schemas/config.schema.yaml)
