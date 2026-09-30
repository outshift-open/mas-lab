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

Contract boundaries are expressed through schema fields such as `design_pattern`,
`governance`, `observability`, `workflow`, and `tools` — there is no separate
`spec.contracts` list.

---

## Shape

```yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: cot-ablation
spec:
  target:
    kind: MAS          # MAS | Agent | Flavour | Infra
    name: optional-filter
  patch:
    workflow:
      entry: broker
      nodes:
        - id: broker
          delegates_to: [researcher]
    agents:
      $entry:            # workflow.entry after this overlay's workflow patch
        design_pattern: { type: cot, params: { max_steps: 10 } }
      $not-entry:        # every agency agent except $entry
        skills: { "$op": { add: [l9-concord-v2-receiver] } }
      $delegates:        # workflow.nodes[$entry].delegates_to
        skills: { "$op": { add: [peer-note] } }
      broker:
        tools: { "$op": { remove: [web-search] } }
    params:
      incident_fixture: example-library:sre-triage-incidents@v2/tool_fixtures/payment-async-timeout.yaml
```

`spec.tools` (outside `patch`) is a separate scenario-level tool injection field.
`target.kind` must be `Agent`, `MAS`, `Flavour`, or `Infra`.

---

## Merge semantics

RFC 7396-style merge on the target resource. Flavour overlays still cannot
select models or API keys (deployment posture only). **Agent** overlays may
patch **any** Agent `spec` field the schema declares (including `models[]`,
sampling, `reasoning`, `extra`, `description`, `behavior`, `tools_ref`).
`spec.models[]` deep-merges by `id`, then `model`, then `main`. Access fields
(`api_base`, `api_key_env`) stay on infra.

Examples: [llm-reasoning.yaml](../schemas/examples/overlays/llm-reasoning.yaml),
[llm-sampling.yaml](../schemas/examples/overlays/llm-sampling.yaml).

On a MAS overlay, `patch.agents.$entry` is applied to `spec.workflow.entry` after this
overlay's `workflow` patch (so a design-pattern overlay need not name the entry agent).
A missing entry, an unknown entry id, or both `$entry` and that id as keys is an error.

A **`target.kind: Agent` overlay applied to a MAS** copies `spec.patch` onto every
nested `spec.agency.agents[]` row (or `spec.agents[]` when agency is absent). Optional
`spec.target.name` selects one row by `id`, `name`, or `metadata.name`
(the agency row id should match the agent YAML `metadata.name` when the same
overlay is reused on both). Zero matches is an error (`OverlayTargetError`) — the overlay must attach somewhere. That is how
labs reuse an Agent overlay such as `with-guardrail` on trip-planner: compose /
`run-mas` merge the overlay into the MAS document, then instantiate merges each
agency row onto the agent YAML (`governance` / `observability` union by plugin id,
they do not replace the agent's existing lists). Lab/bench MAS runs already attach
a shared native sink; a fanned-out default `native` list joins that sink instead of
opening a second `events.jsonl`. Custom observability paths stay per-agent.

On a MAS overlay, reserved `patch.agents` keys expand onto agency ids after this
overlay's `workflow` patch:

| Key | Expands to |
| --- | --- |
| `$entry` | `spec.workflow.entry` |
| `$all` | every `spec.agency.agents` id |
| `$not-entry` | every agency id except `$entry` |
| `$delegates` | `workflow.nodes[$entry].delegates_to` |

They compose in that order, then a named id wins. `$entry` plus that same id as a
key is an error. `$entry` / `$not-entry` require `spec.workflow.entry`. An unknown
`$entry` id is an error.

Merge semantics: later overlays in a scenario stack win on conflicting keys.
Patches use RFC 7396 JSON merge; list fields such as `tools` accept an explicit
`{"$op": {replace|add|remove|clear: [...]}}` form (handled explicitly by the
runtime) alongside plain-list implicit replace.

For MAS overlays, `patch.agents` uses the same operations to modify the MAS
participant list at `spec.agency.agents`. `add` and `replace` entries are
`{id, ref}` agent references, `remove` is a list of agent ids, and `clear: true`
empties the list:

```yaml
target:
  kind: MAS
patch:
  agents:
    $op:
      remove: [schedule_agent]
      add:
        - id: generalist
          ref: ./agents/generalist.yaml
```

The former `agents_add` and `agents_remove` patch fields are not supported; use
`patch.agents.$op` instead.

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

Document-level ``x-*`` keys on the overlay (and under ``spec.patch``) are copied
onto the **target document root**, not into ``spec``. Runtime merge of spec
fields ignores these keys. Later overlays win; nested dicts are RFC 7396-merged.

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
    overlays: {logic: [baseline], control: [], infra: []}
  - id: cot
    overlays: {logic: [cot, no-tools], control: [], infra: []}
```

Tool provider and connection configuration is not patchable through agent
overlays. Remote MCP endpoints belong on infra
[`ToolServerRegistry`](../references/tool-server-registry.md); agent and overlay
schemas reject `providers[]`. See [tool.md](tool.md).

---

## See also

- [plugin-bindings.md](plugin-bindings.md) — string shorthand vs `{type, params}`
- [experiment.md](experiment.md) — scenario overlay stacks
- [compile](../cli/compile.md) — dump the resolved spec
- [ToolContract](../references/tool-contract.md)
- [ToolServerRegistry](../references/tool-server-registry.md)
