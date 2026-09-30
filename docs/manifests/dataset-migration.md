<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Dataset envelope migration

A dataset item is `inputs` + `expectations`. Loaders **still accept** legacy
flat fields (`prompt`, top-level `turns`, `expected_answer`, OpenAI-style
`[{role, content}]` user lists) and emit a deprecation warning that points
here. Rows marked "error" below are rejected at load time. Rewrite before the
next breaking release:

```bash
python scripts/migrate_dataset_envelope.py                  # this repo's datasets
python scripts/migrate_dataset_envelope.py path/to/datasets  # any kind: Dataset file or directory
```

Besides the flat-field rewrite below, it moves app-specific `expectations`
keys under `expectations.details`, collapses a one-key `tool_fixtures`
pointer (`{scene: file.yaml}`) to the path, and drops `spec.item_schema`
(use `spec.schemas`). Ambiguous inputs (several `tool_fixtures` keys, a key
already in `details`) fail with the item id.

## Field map

| Before | After |
|---|---|
| `prompt: "..."` | `inputs.user: "..."` (a **string**, not a role list) |
| `turns: [{role: user, ...}, {role: hitl, ...}]` | user contents → `inputs.user` (string or string list); HITL contents → `inputs.hitl` (string list). Do **not** invent `inputs.turns`. |
| `hitl_responses` | `expectations.details.hitl_responses` (eval), or `inputs.hitl` if they are run inputs |
| `memory_seeds` | `inputs.memory_seeds` (inline list, `{ref:}`, or bare path shorthand) |
| `session_id` | `inputs.session_id` |
| `expected_answer` / `ground_truth` | `expectations.ground_truth` |
| app-specific `expectations.<key>` (error) | `expectations.details.<key>` |
| app-specific keys inside a fixture YAML used as ground truth | `expectations.details` on the **item** |
| overlay `params.<fixture key>` pointing at a fixture file | `inputs.tool_fixtures` on the item (`{ref:}` or bare path) |
| `inputs.user: [{role: user, content: "..."}]` | `inputs.user: "..."` (string) or a list of strings |
| `tool_fixtures` mapping keys other than `by_tool` (error) | `inputs.tool_fixtures: {ref: path}` or `by_tool` |
| inline payload directly under `tool_fixtures` (now an error) | `tool_fixtures: {by_tool: {"*": <payload>}}` |
| tools reading fixture files or environment variables | `mas.runtime.contracts.tool_fixture(ctx, tool_name)`; overlay params in `ctx.runtime_params` |
| bare YAML list of items (no Dataset kind) | `apiVersion: lab/v1` / `kind: Dataset` / `spec.items` |

A string on `user` is the prompt text. A string on `tool_fixtures` /
`memory_seeds` is a path (shorthand for `{ref: that-string}`). Do not mix
the two. `{ref: relative/path}` is the only file-pointer syntax on `user`.

## Couplings

`execution.design.mode: coupled` binds `scenario` to dataset item **`id`**:

```yaml
design:
  mode: coupled
  couplings:
    - scenario: order-42-refund
      items: [order-42-refund]
```

Do **not** rename item ids when migrating. Cartesian / one-factor experiments
that filter by `id` / `group` / `category` keep using those metadata keys.

## Labs already on the envelope

- library-samples trip-planner — `inputs.user` + `expectations.ground_truth`

Evaluators that read app-specific ground truth read it from
`expectations.details` on the Dataset item, never from tool-fixture YAML.
Overlay-only files are not a ground-truth home; if a run needs scoring, it is
a Dataset item.

## Generate-dataset pipeline step

`GenerateDatasetStep` now writes `kind: Dataset` items with `inputs.user`,
not `prompt:`.
