<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Dataset envelope migration

A dataset item is `inputs` + `expectations`. Prefer that envelope now
(`inputs.user` string, `expectations.details` for app-specific ground truth,
catalog `dataset.name`). Loaders **still accept** the deprecated shapes below
and warn once per file. Those shapes will be **removed in a future breaking
release**. Rewrite with:

```bash
python scripts/migrate_dataset_envelope.py                  # this repo's datasets
python scripts/migrate_dataset_envelope.py path/to/datasets  # any kind: Dataset file or directory
```

The migrator also collapses a one-key `tool_fixtures` pointer
(`{scene: file.yaml}`) to the path and drops `spec.item_schema`
(use `spec.schemas`). Ambiguous inputs (several `tool_fixtures` keys, a key
already in `details`) fail with the item id.

## Still accepted — removed later

Codes match `mas.lab.deprecations.NOTICES`. Each warning points here.

| Code | Still loads | Use instead |
|---|---|---|
| `dataset.legacy_item` | Item-level `prompt` / `query` / `question` / `text` / `input` / `user`, top-level `turns`, `expected_answer`, `ground_truth` | `inputs.user` + `expectations.ground_truth` |
| `dataset.role_list_user` | `inputs.user: [{role, content}, …]` | `inputs.user` as a string or list of strings |
| `dataset.legacy_expectations` | App-specific keys on `expectations` (`correct_action`, `governance`, …) | `expectations.details.<key>` |
| `dataset.bare_list` | Bare YAML list of items (no `kind: Dataset`) | `apiVersion: lab/v1` / `kind: Dataset` / `spec.items` |

A clash (`correct_action` both at the top of `expectations` and under
`details`) is an error, not a warning.

Former **lab / experiment wiring** that is not a dataset item, also kept for
this release:

| Still loads | Use instead / notes |
|---|---|
| `experiment.dataset.path` (no `name`) | Still a supported locator. Prefer `dataset.name` (+ `locator`) for catalog datasets. |
| `lab.default_flavour`, `lab.output_dir`, `scenario.user_prompt` | Interactive lab-config only. `output_dir` stays **rejected** on MAS experiments. |

## Field map

| Before | After | Load |
|---|---|---|
| `prompt: "..."` | `inputs.user: "..."` (a **string**, not a role list) | warn `dataset.legacy_item` |
| `turns: [{role: user, ...}, {role: hitl, ...}]` | user contents → `inputs.user` (string or string list); HITL contents → `inputs.hitl` (string list). Do **not** invent `inputs.turns`. | warn `dataset.legacy_item` |
| `hitl_responses` | `expectations.details.hitl_responses` (eval), or `inputs.hitl` if they are run inputs | warn `dataset.legacy_item` |
| `memory_seeds` | `inputs.memory_seeds` (inline list, `{ref:}`, or bare path shorthand) | warn `dataset.legacy_item` |
| `session_id` | `inputs.session_id` | warn `dataset.legacy_item` |
| `expected_answer` / `ground_truth` | `expectations.ground_truth` | warn `dataset.legacy_item` |
| app-specific `expectations.<key>` | `expectations.details.<key>` | warn `dataset.legacy_expectations` |
| app-specific keys inside a fixture YAML used as ground truth | `expectations.details` on the **item** | migrate |
| overlay `params.<fixture key>` pointing at a fixture file | `inputs.tool_fixtures` on the item (`{ref:}` or bare path) | migrate |
| `inputs.user: [{role: user, content: "..."}]` | `inputs.user: "..."` (string) or a list of strings | warn `dataset.role_list_user` |
| `tool_fixtures` mapping keys other than `by_tool` | `inputs.tool_fixtures: {ref: path}` or `by_tool` | **error** |
| inline payload directly under `tool_fixtures` | `tool_fixtures: {by_tool: {"*": <payload>}}` | **error** |
| tools reading fixture files or environment variables | `mas.runtime.contracts.tool_fixture(ctx, tool_name)`; overlay params in `ctx.runtime_params` | — |
| bare YAML list of items (no Dataset kind) | `apiVersion: lab/v1` / `kind: Dataset` / `spec.items` | warn `dataset.bare_list` |

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
