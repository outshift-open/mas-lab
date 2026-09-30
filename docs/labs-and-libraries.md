<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Labs, libraries, and local plugins

A **lab** is an experiment pack. A **library** is reusable code and YAML.
Do not turn a lab into a library, and do not create a library when you only
need an experiment.

**Datasets.** `library-samples` publishes the complete reusable pack for the
reference app (`trip-planner-benchmark`). CI, unit tests, and functional
tests pin that catalog (`locator: samples`) and cap rows with
`dataset.limit`. They must not `path:` into `labs/` — paper labs are not
shipped with the packages. Experiment-specific packs (QA reasoning, MAS
necessity, lifecycle queries, extensions) live under that lab’s `datasets/`
and are referenced only from the lab itself.

Developer discovery contract: [library-discovery.md](library-discovery.md).

---

## Lab

A lab is a `*.lab/` folder with `lab-config.yaml`. It stays flat: scenarios,
overlays, datasets, and pipelines. Refs use `name:path` (for example
`samples:tools/calc.tool.yaml`).

Paper labs live under [`labs/`](../labs/README.md). Create a lab when you are
composing a campaign, not when you are publishing reusable tools.

## Library

A library is a folder with `library.yaml`. Apps, tools, overlays, plugins,
and Python live there. In a `name:path` ref, `name` is always a **library
name** (`samples`, `standard`, `lab`, `skills`, `ioa`, or a lab-local name
such as `lib`). It is never a filesystem path. Unknown names fail.

Shipped libraries in this repo include `library-samples/`,
`library-standard/`, `library-lab/`, `library-skills/`, and `library-ioa/`.
The name you write in YAML is a **library scheme** (`samples`, `library-ioc`),
not necessarily the Python package name (`mas-library-samples`). Additional
names can be listed as `aliases:` in `library.yaml`; the directory basename
and `name:` field are also accepted. Labs then pin a MAS with
`library:app` (for example `library-ioc:sre-triage@v2`). Versioning uses
`name@version` (bare name is `@latest`). Slash is a path
(`library-ioc:apps/sre-triage/v2`), not an id alias.

How to write those refs: [writing-manifests.md](manifests/writing-manifests.md).

A library **may live inside a lab**. That does not make the lab itself a
library — do not put `library.yaml` on the lab root.

## Local plugins

A **plugin** is a runtime or pipeline extension **registered by a library**.
Put plugin Python and YAML *in* a library (lab-local or shipped). Do not
invent a third top-level “plugins folder” beside lab vs library.

| What you are adding | Where it lives |
| --- | --- |
| One-off bench/pipeline step for this experiment | That lab’s local library (catalogued in `library.yaml`) |
| Agent/runtime plugin (design pattern, memory, tool provider, …) | Declared in that library’s `library.yaml` so discovery finds it |
| Experiment pack (scenarios, overlays, lab-owned datasets) | The lab, not a library |

A pipeline step is still a plugin of type `step`. The lab is the experiment
surface; the library is what registers the step.

---

## When to use which

1. **Lab is sufficient** when you only compose existing libraries: experiments,
   overlays, datasets, refs like `samples:tools/calc.tool.yaml`. No new
   reusable code.
2. **Local library inside the lab** when this lab needs reusable manifests,
   tools, plugins, or code that are not (yet) worth a shipped package. Put
   them in a subdir with `library.yaml`, list it in `lab.libraries`, ref as
   `name:path`.
3. **Shipped / workspace library** when more than one lab (or ctl/runtime
   generally) should reuse it: an installable package, or a path in workspace
   `config.yaml` `manifest_libraries:`.
4. **Local plugins** live *inside* a library (option 2 or 3), not instead of
   one. If it is only a bench step for this experiment, keep it in the lab’s
   local library. If it is an agent/runtime plugin, declare it in that
   library’s `library.yaml`.

---

## Lab-local library (in-repo pattern)

`labs/lifecycle-control.lab` and `labs/extensions.lab` keep reusable pipeline
code in `lib/` and list that directory:

```yaml
# lab-config.yaml
lab:
  name: lifecycle-control
  libraries:
    - lib/
```

```yaml
# lib/library.yaml
apiVersion: mas/v1
kind: Library

name: lifecycle-control-lib
description: Lab-local pipeline figure steps for this lab.
version: "0.1.0"
```

The library name in refs is the listed basename: `lib/` → `lib`. Immediate
children of the lab root that contain `library.yaml` are picked up too (any
directory name; `lib/` is not required).

A listed directory **without** `library.yaml` is Python `sys.path` only. Do
not leave an in-repo lab in that state.

## How to write `name:path`

```yaml
# Overlay / experiment / agent — prefix is a library name
tools:
  - samples:tools/calc.tool.yaml

application:
  app: library-ioc:sre-triage@v2
  # or: manifest: samples:apps/trip-planner/mas.yaml

# Workspace config.yaml — search folders (library root or parent of libraries)
manifest_libraries:
  - .
  - ./libraries
```

Lab-local names win over the same name in workspace config or an installed
library. First-seen name wins.

`lab.libraries`, workspace `manifest_libraries`, and `MAS_LIBRARY_PATHS` are
the same scan. Install (entry point) is the other door. `library.yaml`
fills the catalog. Do not declare aliases (`ioc` for `library-ioc`).

---

## See also

- [How to write manifests](manifests/writing-manifests.md) — inline vs file vs `LIBRARY:` id
- [User configuration](user-config.md) — workspace `config.yaml` and path vars
- [Lab manifests](manifests/lab.md) — `lab-config.yaml` fields
- [Tutorial 1](tutorials/01-building-an-agent/README.md) — overlay `name:path` refs
- [Package map](libraries.md) — installable wheels
- [Library discovery](library-discovery.md) — search order and `library.yaml` contract
