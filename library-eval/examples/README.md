<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Examples (mas-library-eval)

Small feature scenarios for MCE evaluation — closer to functional tests than
to sample apps. Layout: `examples/<category>/<name>/`.

Tests load these as fixtures. `mas-ctl validate` works from the repo root.

**Not here:** trip-planner / SRE apps. Those live in `library-samples/apps/`.

## Index

| Category | Example | Kind | What it shows |
|----------|---------|------|----------------|
| [mce](mce/) | [judge-override](mce/judge-override/) | Experiment | `eval_mce` judge model vs agent model |
