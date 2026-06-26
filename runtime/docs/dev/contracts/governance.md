<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Governance Contracts

Policy boundaries applied **before and after** capability contracts fire.
Governance plugins raise `PolicyViolation` to deny; the kernel maps decisions
to egress chokepoints.

See also: [governance-policy-engine.md](../../governance-policy-engine.md) ·
[semantic-protocols.md](../../semantic-protocols.md) · [mealy-envelope.md](../../mealy-envelope.md)

---

## Design principle

Governance contracts are **orthogonal** to capability contracts. You can add
budget or routing rules without changing tool or model plugins.

In the v2 kernel, egress policy is evaluated in
`kernel/envelope.py` (`_evaluate_egress`, `_evaluate_ingress`) at
`GOVERNANCE_AUTHORIZE` / `GOVERNANCE_VALIDATE` symbols. `GovEnvelopeMachine`
records state and telemetry on those symbols; the imperative evaluation runs in
the envelope coordinator (see `gov_envelope.py` module docstring).

---

## BudgetContract

Token, cost, and call-rate ceilings over the **lifetime of a run** (monotonic
counters — distinct from Petri-net rate limits).

| Method | When |
|--------|------|
| `on_pre_llm_call(ctx)` | Before model egress |
| `on_post_llm_call(ctx)` | After model response |
| `on_pre_tool_call(ctx)` | Before tool egress |
| `get_usage()` | Inspect current counters |

---

## Internal governance extensions (not in OSS)

**Sandbox** (filesystem/shell/network isolation) and **TBAC** (task-based access
control) are proprietary extensions. Contract specs and reference implementations
live in the sibling `mas-lab-internal` repository (`docs/contracts/sandbox-contract.md`,
`docs/contracts/tbac-contract.md`). OSS tutorials and paper labs use budget caps,
guardrails, and HITL only.

---

## RoutingContract

Agent-to-agent edge policy (topology / delegate visibility).

| Method | Purpose |
|--------|---------|
| `check(from_agent, to_agent, message_kind)` | Allow/deny routing |

---

## Declarative policies

For YAML-driven governance (HITL, content filters, budget triggers), use the
**Governance Policy Engine** plugin — see
[governance-policy-engine.md](../../governance-policy-engine.md). It composes
`trigger × evaluation × action` and attaches to hook phases.

---

## Mealy envelope mapping

Every governed egress walks:

```text
GOV_AUTHORIZE_START → GOVERNANCE_AUTHORIZE → GOV_AUTHORIZE_END
  → … execute …
GOV_VALIDATE_START → GOVERNANCE_VALIDATE → GOV_VALIDATE_END
```

Observability summand records `governance.decision` events at before/after
checkpoints. Disable governance with `mas-ctl chat --without-gov` (collapses σ).

---

## Implementation status

| Contract | v2 kernel chokepoint | Notes |
|----------|---------------------|-------|
| Budget | Via policy engine / sample gov | Manifest `governance.policies` |
| Routing | MAS transport | Workflow-level |

Plugins may declare `governed_by: ["budget"]` in manifest metadata;
the runtime validates wiring at load time. Sandbox and TBAC governance ids are
reserved for internal extensions (see above).
