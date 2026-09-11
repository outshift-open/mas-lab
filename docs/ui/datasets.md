<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Datasets

A dataset is a YAML manifest listing benchmark inputs — prompts, expected ("ground truth")
answers, and grouping metadata — that an **experiment** pairs with scenarios and runs against a
MAS. In the sidebar it sits between **Pipelines** and **Overlays**: Applications → Playground →
Experiments → Pipelines → **Datasets** → Overlays → Control Panel.

## Where to find it

- `/:library/datasets` — the datasets table
- `/:library/datasets/_create` — create a new dataset
- `/:library/datasets/*` — view/edit an existing dataset (wildcard path so nested/relative file
  names under `datasets/` resolve correctly)

## What you can do here

**Datasets table.** Lists every dataset YAML file (`.yaml`/`.yml`) in the library with its
relative path (as **Name**, truncated with a full-path tooltip) and **Description**. Clicking a
row's name opens it for editing. The row action menu offers **Delete**; you can also select
multiple rows and use **Delete Selected (N)**. Either path opens a confirmation dialog ("This
action cannot be undone") before removing anything. Use **Add Dataset** to start a new one.

**Dataset editor.** Both the "new" and existing-dataset pages share the same item editor. Each
item has:

- **ID**, **Category**, **Group** — plain text fields
- **Prompt** and **Ground Truth** — multiline text fields
- **Target Agents** and **Tags** — chip-style inputs; type a value and press Enter to add it as a
  chip, click a chip's `x` to remove it

Items are listed with an **Add Item** button to append a new one, and each item card has a
trash/delete icon to remove it. Once there are more than 20 items, a page selector appears below
the list. The page header shows **Save** (opens a dialog for the dataset's **Name** and
**Description** before writing the file) and, for existing datasets, **Delete**.

!!! note
    The manifest on disk is the nested `Dataset` YAML shape (`metadata` + `spec.items`, each item
    carrying `inputs.user[].content` and `expectations.ground_truth`), but the editor works with a
    flattened, per-item JSON model (`prompt`, `ground_truth`, `group`, `target_agents`, `category`,
    `tags`). The page converts between the two on load and on save.

## Task walkthrough

Create a dataset and add items:

1. From the Datasets table, click **Add Dataset**.
2. Click **Add Item** to create your first item.
3. Fill in **Prompt** (required) and, if you have one, **Ground Truth**.
4. Optionally set **Category** and **Group**, and add **Target Agents** / **Tags** by typing a
   value and pressing Enter.
5. Repeat **Add Item** for each additional Q&A/prompt item you need.
6. Click **Save**, give the dataset a **Name** (and optional **Description**) in the dialog, and
   confirm — this creates the dataset file and returns you to it under its saved name.
7. To remove an item later, use its delete icon; to remove the whole dataset, use **Delete** on
   the page header (or from the Datasets table's row menu).

## Related

- [Dataset manifest](../manifests/dataset.md)
- [Experiments](experiments.md) — datasets are consumed by experiments as benchmark input
- [Web UI overview](index.md)
