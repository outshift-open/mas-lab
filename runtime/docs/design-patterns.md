<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Design patterns

Reasoning patterns (ReAct, chain-of-thought, plan/execute, tree-of-thoughts, and others) are
**runtime plugins** registered in `mas-library-standard` and selected from agent manifests or
**overlays** (`kind: Overlay`).

## Enable via overlay

```yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: react
spec:
  patch:
    design_pattern:
      type: react
```

See `library-samples/overlays/` for working examples.

## Plugin implementations

Design-pattern plugins live under `runtime/src/mas/runtime/machines/design_pattern/plugins/`
(`react.py`, `cot.py`, `plan_execute.py`, `tree_of_thoughts.py`, …). Each implements the Mealy
design-pattern contract and composes with governance and observability on the kernel envelope path.

Integration tests: `runtime/tests/integration/test_design_pattern_plugins_integration.py`.

## Formal model

The design-pattern automaton \(M_{dp}\) is one factor in the runtime product. See
[automaton-product-model.md](automaton-product-model.md) and
[mealy-product-formal-design.md](mealy-product-formal-design.md).

## Tutorials

- [Building an agent](../../docs/tutorials/01-building-an-agent/)
- [Creating a MAS](../../docs/tutorials/02-creating-a-mas/)

## Related

- [production-path.md](production-path.md) — supported execution path
- [plugin-and-tool-authoring.md](plugin-and-tool-authoring.md) — writing plugins
- [contracts-reference.md](contracts-reference.md) — contract families
