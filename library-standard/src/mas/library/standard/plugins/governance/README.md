<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Governance / HITL operator plugins (HitlResponder contract)

Manifest `spec.governance.hitl_mode` selects the operator plugin at ctl bootstrap.

| Plugin id | Contract | Wired at | Use |
|-----------|----------|----------|-----|
| `hitl-auto-approve@v1` | `HitlResponder` | `KernelDriver.hitl` | CI, batch, `-q` runs |
| `hitl-auto-deny@v1` | `HitlResponder` | `KernelDriver.hitl` | Negative tests |
| `hitl-interactive@ctl` | `HitlTerminal` | ctl session boundary | TTY / TUI operator |
| `gov_no_undeclared_tool` | `GovernancePlugin` | `spec.governance` chain | BLOCK tool names not in this LLM call's `tools` list (pass otherwise); reason is fed back as a tool observation. Example: [examples/governance/undeclared-tool/](../../../../../../examples/governance/undeclared-tool/). Overlay: `with-hardened`. |

Plugin card: [no-undeclared-tool.md](no-undeclared-tool.md).
Overlay index: [../../overlays/README.md](../../overlays/README.md).

Kernel emits `EmitHitlRequest` only from `M_gov` egress gate. Only `M_gov` enters `HITL_PENDING`.
`M_tool` enters `WAIT_GOV`; `M_dp` stays `AWAITING_INGRESS` (waiting on the tool chain).
