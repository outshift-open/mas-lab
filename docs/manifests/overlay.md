<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Overlay manifest (`kind: Overlay`)

**Package:** `mas-runtime` · **Schema:** `overlay.schema.yaml` · **apiVersion:** `mas/v1`

An **overlay** is a manifest that patches an **agent**, **MAS**, or **flavour** manifest
without copying the whole file. **Experiments** reference overlays per **scenario**
(`scenarios[].overlays`); the CLI applies them with `-o path/to/overlay.yaml`.

**Terms:** [glossary.md](../glossary.md)

Symmetrical partial or full override of Agent, MAS, or Flavour documents. Used as
benchmark **scenarios**, runtime overlays, and UI overlay builder output.

Contract boundaries are expressed through existing schema fields (`design_pattern`, `plugins`,
`workflow`, `tools`, governance blocks) — there is no separate `spec.contracts` list.

---

## Shape

```yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: cot-ablation
spec:
  target:
    kind: MAS          # MAS | Agent | Flavour | any
    name: optional-filter
  patch:
    design_pattern: { type: cot, config: { max_steps: 10 } }
    agents:
      broker:
        tools: { "$op": { remove: [web-search] } }
    workflow: { ... }   # topology replacement
    params:
      incident_fixture: datasets/fixtures/timeout.yaml
  tools: []            # inject tools (scenario level)
```

---

## Merge semantics

RFC 7396-style merge on the target resource. Separation rules reject model endpoints,
api keys, and raw system-prompt rewrites in `patch` (use agent `role` / overlay agent blocks).

Merge semantics: later overlays in a scenario stack win on conflicting keys.
Patches use RFC 7396 JSON merge; list fields such as `tools` accept an explicit
`{"$op": {replace|add|remove|clear: [...]}}` form (handled explicitly by the
runtime) alongside plain-list implicit replace.

`context` (prompt/role text) gets the same `$op` sugar, but per chunk name.
Each `spec.context.<key>` value may be a plain string/`{ref}` (implicit full
replace, same as always) or a list of fragments — a `$op` patch operates on
that fragment list, so an overlay can append or drop one line without
restating the rest of the base prompt:

```yaml
patch:
  context:
    role: {"$op": {"add": ["Escalate P1 incidents immediately."]}}
    # remove: ["Escalate P1 incidents immediately."]
    # replace: ["Whole new role text."]
    # clear: true
```

---

## Experiment linkage

```yaml
scenarios:
  - id: baseline
    overlays: [baseline]      # resolves to overlays/baseline.yaml
  - id: cot
    overlays: [cot, no-tools] # stack order matters
```

---

## See also

- [experiment.md](experiment.md) — scenario overlay stacks
- [experiment.md](experiment.md)
