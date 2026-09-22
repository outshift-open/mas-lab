<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Examples

Small feature scenarios for plugins in this library — closer to functional
tests than to sample apps.

Layout: `examples/<category>/<name>/`. `<category>` is a plugin kind
(`governance`, `observability`, `design-pattern`, `memory`, `workflow`,
`tools`). Add the folder when the first example lands. Each `<name>/` is a
runnable **Agent** or **MAS** that pins one failure mode.

Tests load these as fixtures. `mas-ctl validate` / `mas-ctl chat` (or
`run-mas`) work from the repo root.

**Not here:** real use-case MAS (trip planner, SRE triage, …). Those live
in `library-samples/apps/` and are registered in that library's
`library.yaml`. Do not catalog plugin examples as apps.

## Index

| Category | Example | Kind | What it shows |
|----------|---------|------|----------------|
| [governance](governance/) | [undeclared-tool](governance/undeclared-tool/) | Agent | `gov_no_undeclared_tool` BLOCKs a name not in this LLM call's `tools` list |
