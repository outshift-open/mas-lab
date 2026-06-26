<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Workflow manifest (`kind: Workflow`, `workflow/v1`)

**Package:** `mas-runtime` · **Schema:** `workflow.schema.yaml`

Graph-form workflow document (`nodes` + `edges`). Most apps embed workflow under
`MAS.spec.workflow` instead.

See **[Topology, workflow, and routing](topology-and-workflow.md)** for how this
relates to team **topology** (design-space overlays) and **routing** policy.

---

## OSS execution paths

| Pattern | How it runs |
| --- | --- |
| Single entry agent | `mas-ctl chat` / `mas-ctl run-mas` |
| Sequential graph | `mas-ctl run-mas` with `nodes` + `edges` |
| Dynamic delegation | Default multi-agent — entry agent drives delegation tools |
| Moderator-broker topology | `workflow.entry: moderator` + `delegates_to` (design-space Exp 1.2) |

```yaml
spec:
  workflow:
    entry: moderator
    nodes:
      - {id: moderator, agent: moderator}
      - {id: researcher, agent: researcher}
    edges:
      - {from: moderator, to: researcher}
```

---

## API

`GET /api/schemas/workflow`

---

## See also

- [MAS manifest](mas.md)
- [Topology, workflow, and routing](topology-and-workflow.md)
