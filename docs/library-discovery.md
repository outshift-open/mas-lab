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

## Search order

First-seen name wins. Lab-local wins over workspace and installed libraries
of the same name.

1. **Lab-local** — from the enclosing `lab-config.yaml` (`find_lab_dir`):
   `lab.libraries` directories that contain `library.yaml`, plus **immediate**
   children of the lab root that contain `library.yaml` (any directory name).
   The library name is the listed basename (`lib/` → `lib`) or the child
   directory name. A listed directory **without** `library.yaml` is Python
   `sys.path` only (no library name). A listed name that is already a known
   library (`samples`) keeps resolve-by-name behaviour via later steps.
2. **Workspace config** — `config.yaml` `manifest_libraries:` (library name →
   path relative to the workspace root).
3. **Installed libraries** — libraries registered in the environment.
4. **`MAS_LIBRARY_PATHS`** — `os.pathsep`-separated roots or parents of
   sibling library folders. Names are directory basenames.
5. **Ancestor walk** — upward from anchors/cwd for `library.yaml`, stopping
   at `.git` and `.lab`. A `library.yaml` on the lab root is not
   dual-registered (skipping that file is intentional). `.git` is a walk
   boundary, not a search root — sibling `library-*` checkouts are not scanned.

`inject_lab_libraries` still puts the lab root and listed library directories
on `sys.path`, including a listed dir that has no `library.yaml`.

---

## `library.yaml` contract

Schema: [`docs/schemas/library.schema.yaml`](schemas/library.schema.yaml).
Kind `Library`, `apiVersion: mas/v1`, flat (no `metadata:` / `spec:`).

| Field | Role |
| --- | --- |
| `name` | Package-style identity (`mas-library-samples`, `lifecycle-control-lib`) |
| `apps` / `datasets` / `tools` | Catalogs for `name:path` and `app:` lookup |
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

## See also

- [Labs vs libraries](labs-and-libraries.md)
- [User configuration](user-config.md)
- [lab-config schema](schemas/lab/lab-config.schema.yaml)
- [workspace config schema](schemas/config.schema.yaml)
