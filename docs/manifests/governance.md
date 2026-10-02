<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Governance (`spec.governance`)

Companion to the [Agent manifest](agent.md) — this is **not** a YAML kind.
How to write plugin entries: [plugin-bindings.md](plugin-bindings.md).
Schema: [`governance-binding.schema.yaml`](../schemas/runtime/fragments/governance-binding.schema.yaml).
Dev contracts: [runtime/docs/dev/contracts/governance.md](../../runtime/docs/dev/contracts/governance.md).

**Retries, circuit breaker, `error_policy` defaults, overlay, and logging**
are documented once: [reliability.md](../references/reliability.md).

---

## Chain

`spec.governance` is an **iptables-style chain**: BLOCK stops and returns
that error; ALLOW passes to the next plugin. `spec.observability` is a
**sequence** (every plugin always runs).

| Layer | When | Who |
|-------|------|-----|
| Infra retry | Inside the LLM HTTP POST / tool invocation | `spec.control.retry` |
| Circuit breaker | After infra retries on `unavailable` | library plugin via `spec.control.circuit_breaker` (default `threshold`) |
| Egress chain | Before the engine call (`TOOL_CALL`, `LLM_CALL`) | plugins in `spec.governance[]` |
| Ingress `error_policy` | After `_end`, on engine `ERROR` | `retry_on_error` (plugin), if installed |

Do not put retry budgets on the egress chain. Infra retries the *same*
call; ingress `error_policy.transient: retry` re-schedules a new envelope
step (up to `max_gov_retries`). Engine retry defaults:
[reliability.md](../references/reliability.md#defaults-bare-agent-no-overlay).

Without `error_recovery_plugin`, ERROR follows `gov_ingress_profile`
(default `PERMISSIVE` → ALLOW). The kernel does not interpret
`error_policy`; that table is plugin config. The named recovery plugin
is installed on the ingress chain — it is not a kernel slot.

---

## Shipped plugins

| Plugin | Role | Card |
|--------|------|------|
| `gov_no_undeclared_tool` | Egress BLOCK if the tool name was not in this LLM call's `tools` list | [no-undeclared-tool.md](../../library-standard/src/mas/library/standard/plugins/governance/no-undeclared-tool.md) |
| `retry_on_error` | Ingress: `error_policy.<class>` → allow/retry/block/skip. Egress always PASSes | [retry-on-error.md](../../library-standard/src/mas/library/standard/plugins/governance/retry-on-error.md) |
| `sample_governance` | HITL / destructive flags | library-standard sample |

`error_recovery_plugin` and `error_policy` are flattened from any stanza
(same as `hitl_on_tool`). The recovery plugin goes on the ingress chain;
the kernel never stores a plugin instance of its own. Put them on
`retry_on_error`, or apply `with-hardened` (appends both governance
plugins and merges `control.retry` / `circuit_breaker`, which loads the
`threshold` circuit-breaker plugin):
[reliability.md](../references/reliability.md#with-hardened).

```yaml
governance:
  - gov_no_undeclared_tool
  - retry_on_error:
      error_recovery_plugin: retry_on_error
      error_policy:
        transient: retry
        unavailable: retry
        application: allow
        fatal: block
```

Empty chain (`[]`) is the default. Ingress/egress decisions are
`kind: governance_decision` in native `events.jsonl`. Typed failures
also carry `failure_class`, `failure_code`, and `retry_attempts`. Infra
re-attempts are logs on `mas.runtime.reliability`, not extra governance
events — [reliability.md § Logging](../references/reliability.md#logging).
