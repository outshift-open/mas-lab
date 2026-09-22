<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Overlays (MAS Library Standard)

Index of every overlay shipped in this package. Each file is a `kind: Overlay`
manifest (`apiVersion: mas/v1`) merged onto an agent with `-o`.

Packaged URI: `pkg://mas.library.standard/overlays/<file>`.

Checkout path: `library-standard/src/mas/library/standard/overlays/<file>`.

| File | `metadata.name` | Target | What it does |
|------|-----------------|--------|----------------|
| `observability-native.yaml` | `observability-native` | Agent | Writes native `events.jsonl` (`spec.observability` → `native`). |
| `with-hardened.yaml` | `with-hardened` | Agent | Appends `gov_no_undeclared_tool` to the `spec.governance` chain (`$op.add`). |

`spec.observability` is a sequence (every plugin sees every event).
`spec.governance` is a chain: BLOCK stops and returns the error; ALLOW
passes to the next plugin. `with-hardened` uses `$op.add`, so it keeps any
governance plugins already on the agent:

```bash
mas-ctl chat agent.yaml \
  -o pkg://mas.library.standard/overlays/with-hardened.yaml \
  -o pkg://mas.library.standard/overlays/observability-native.yaml
```

CLI shortcut `--events` is equivalent to `observability-native` for one run.
See [docs/cli/observability.md](../../../../../../../docs/cli/observability.md).

`gov_no_undeclared_tool` example (not a sample app):
[examples/governance/undeclared-tool/](../../../../../examples/governance/undeclared-tool/).
