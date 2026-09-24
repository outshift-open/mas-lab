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
    design_pattern: cot      # string shorthand ≡ {type: cot}; or {type: cot, params: {max_steps: 10}}
    agents:
      $entry:            # workflow.entry after this overlay's workflow patch
        design_pattern: { type: cot, params: { max_steps: 10 } }
      broker:
        tools: { "$op": { remove: [web-search] } }
    workflow: { ... }   # topology: entry + directed delegation links
    params:
      incident_fixture: datasets/fixtures/timeout.yaml
  tools: []            # inject tools (scenario level)
```

---

## Merge semantics

RFC 7396-style merge on the target resource. Separation rules reject model endpoints,
api keys, and raw system-prompt rewrites in `patch` (use agent `role` / overlay agent blocks).

On a MAS overlay, `patch.agents.$entry` is applied to `spec.workflow.entry` after this
overlay's `workflow` patch (so a design-pattern overlay need not name the entry agent).
A missing entry, an unknown entry id, or both `$entry` and that id as keys is an error.

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
    role:
      $op:
        add:
          - "Escalate P1 incidents immediately."
        # remove:
        #   - "Escalate P1 incidents immediately."
        # replace:
        #   - "Whole new role text."
        # clear: true
```

---

## Inspect the compiled spec

```bash
mas-ctl compile agent.yaml -o overlays/tools.yaml -o overlays/skills.yaml
mas-ctl compile mas.yaml -o overlays/linear.yaml -O ./compiled/
```

`--layout bundle` inlines MAS agents into one YAML file; the default for a
directory `--output` keeps `mas.yaml` plus `agents/*.yaml`. See
[compile](../cli/compile.md).

---

## Experiment linkage

```yaml
scenarios:
  - id: baseline
    overlays: [baseline]      # resolves to overlays/baseline.yaml
  - id: cot
    overlays: [cot, no-tools] # stack order matters
```

`patch.providers` claims remote or local tool plugins (`kind` + `tools`).
Connection URL, headers, timeout, pagination, and list-cache policy belong on
infra [`ToolServerRegistry`](../references/tool-server-registry.md) when shared;
an overlay may set `url` on `providers[]`. When both overlay and infra set a
key, the overlay value is used. See [tool.md](tool.md).

---

## See also

- [plugin-bindings.md](plugin-bindings.md) — string shorthand vs `{type, params}`
- [experiment.md](experiment.md) — scenario overlay stacks
- [compile](../cli/compile.md) — dump the resolved spec
- [ToolContract](../references/tool-contract.md)
- [ToolServerRegistry](../references/tool-server-registry.md)
