<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Dataset envelope migration

A dataset item is `inputs` + `expectations`. Loaders **still accept** legacy
flat fields (`prompt`, top-level `turns`, `expected_answer`, OpenAI-style
`[{role, content}]` user lists, `tool_fixtures.incident_fixture`) and emit a
deprecation warning that points here. Rewrite before the next breaking
release:

```bash
python scripts/migrate_dataset_envelope.py
```

## Field map

| Before | After |
|---|---|
| `prompt: "..."` | `inputs.user: "..."` (a **string**, not a role list) |
| `turns: [{role: user, ...}, {role: hitl, ...}]` | user contents → `inputs.user` (string or string list); HITL contents → `inputs.hitl` (string list). Do **not** invent `inputs.turns`. |
| `hitl_responses` | `expectations.governance.hitl_responses` (eval), or `inputs.hitl` if they are run inputs |
| `memory_seeds` | `inputs.memory_seeds` (inline list, `{ref:}`, or bare path shorthand) |
| `session_id` | `inputs.session_id` |
| `expected_answer` / `ground_truth` | `expectations.ground_truth` |
| `correct_action` inside a fixture YAML | `expectations.correct_action` on the **item** |
| overlay `params.incident_fixture` | `inputs.tool_fixtures` on the item (`{ref:}` or bare path) |
| `inputs.user: [{role: user, content: "..."}]` | `inputs.user: "..."` (string) or a list of strings |
| `tool_fixtures.incident_fixture: path` | `inputs.tool_fixtures: {ref: path}` or `by_tool` |
| bare YAML list of items (no Dataset kind) | `apiVersion: lab/v1` / `kind: Dataset` / `spec.items` |

A string on `user` is the prompt text. A string on `tool_fixtures` /
`memory_seeds` is a path (shorthand for `{ref: that-string}`). Do not mix
the two. `{ref: relative/path}` is the only file-pointer syntax on `user`.

During the compatibility window, the loader resolves the deprecated
`tool_fixtures.incident_fixture` payload for runtime consumers while retaining
its original reference for benchmark adapters that expose a filesystem
sidecar. New datasets should use `inputs.tool_fixtures: {ref: ...}` or a
`by_tool` mapping.

## Couplings

`execution.design.mode: coupled` binds `scenario` to dataset item **`id`**:

```yaml
design:
  mode: coupled
  couplings:
    - scenario: routing-policy-rollback
      items: [routing-policy-rollback]
```

Do **not** rename item ids when migrating. Cartesian / one-factor experiments
that filter by `id` / `group` / `category` keep using those metadata keys.

## Labs already on the envelope

- library-ioc SRE datasets (`sre-triage-scenarios@v1`, …) — `inputs.user` +
  `tool_fixtures` + `expectations.correct_action`
- library-samples trip-planner — `inputs.user` + `expectations.ground_truth`
- coding-agent notification-delivery — `inputs.user` + custom expectations

OSS trip-planner eval that reads `expectations.ground_truth` does not change.
SRE eval reads `expectations.correct_action` on the Dataset item. It does not
read `correct_action` from tool-fixture YAML. Overlay-only scene files are
not a ground-truth home; if a scene needs scoring, it is a Dataset item.

## Generate-dataset pipeline step

`GenerateDatasetStep` now writes `kind: Dataset` items with `inputs.user`,
not `prompt:`.
