<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Reliability: retries, circuit breaker, error policy

**This is the full reference** for LLM/tool failure handling (retries,
circuit breaker, `error_policy`, defaults, logging). It is a runtime
topic, not a YAML kind — agent field lists stay on
[agent.md](../manifests/agent.md). Governance chain and plugins:
[governance.md](../manifests/governance.md). Infra proxy retry:
[infra.md](../manifests/infra.md).

Two layers share one taxonomy (`transient` / `unavailable` /
`application` / `fatal`) so infra retry, the circuit breaker, and ingress
governance never disagree about *what happened*.

| Layer | Where | What it does |
|-------|--------|----------------|
| **Infra** | LLM HTTP client + tool dispatch | Re-issue the same call (`RetryPolicy`). After the budget is spent, optional **circuit breaker** plugin on `unavailable`. |
| **Governance** | Ingress after `_end` | `error_policy` maps the typed failure onto `allow` / `retry` / `block` / `skip`. Plugin: `retry_on_error`. |
| **Lab** | `mas-lab benchmark run` | Re-issue a failed scenario×item×run (`execution.max_attempts`, default 3). Independent of `n_runs`. |

Application tool errors stay a `TOOL_RESULT` (working memory). Exhausted
LLM failures stay `ERROR`. Unknown tool names are `application` /
`TOOL_UNKNOWN`, not circuit-breaker `unavailable`.

Schema: [`control-binding.schema.yaml`](../schemas/runtime/fragments/control-binding.schema.yaml),
[`retry-policy.schema.yaml`](../schemas/runtime/fragments/retry-policy.schema.yaml).
Engine helpers: `mas.runtime.reliability` (taxonomy, classify, infra retry).
LLM HTTP POST lives in the `llm_provider` plugin (`mas.library.standard.plugins.llm.http`).
Circuit breaker plugin: `mas.library.standard.plugins.reliability.circuit_breaker`.
Logger: `mas.runtime.reliability`.

---

## Defaults (bare agent, no overlay)

Seamless for ordinary chat and LLM HTTP: a dropped socket, connect-refused,
or HTTP 500 is retried; a tool `ValueError` is shown to the model; a bad TLS
setup stops the turn.

| Knob | Default |
|------|---------|
| LLM `max_attempts` | `4` (env `MAS_LLM_HTTP_RETRIES` default `3` extra retries → 4 attempts) |
| LLM `retry_on` | `[transient, unavailable]` |
| LLM `backoff_s` / `backoff_multiplier` / `jitter` | `0.5` / `2.0` / `true` |
| LLM `require_idempotent` | `false` (HTTP POST of the same payload is treated as idempotent) |
| LLM `max_backoff_s` | unlimited |
| Tools `max_attempts` | `2` |
| Tools `retry_on` | `[transient, unavailable]` |
| Tools `require_idempotent` | `true` (transient retries only if `spec.tools[].idempotent` / Tool YAML) |
| Circuit breaker | **off** (omit `spec.control.circuit_breaker`, or set `null`) |
| Ingress (no recovery plugin) | `gov_ingress_profile` **PERMISSIVE** (ALLOW engine ERROR) |
| `error_policy.*` | **unset** until `retry_on_error` is installed |
| `error_recovery_plugin` | unset |
| `max_gov_retries` | `2` |
| Lab run `max_attempts` | `3` (`experiment.execution.max_attempts`; set `1` to disable) |
| `spec.budget.max_llm_calls` / `max_tool_calls` | unset (no call-count ceiling) |

### `with-hardened`

`pkg://mas.library.standard/overlays/with-hardened.yaml` keeps the infra
retry defaults and turns on governance + the breaker + call-count caps
— this is the recommended overlay for production posture:

| Knob | Value |
|------|--------|
| Egress | append `gov_no_undeclared_tool` |
| Ingress | append `retry_on_error` with `error_recovery_plugin: retry_on_error` |
| `error_policy` | transient/unavailable → `retry`; application → `allow`; fatal → `block` |
| Circuit breaker | on; `failure_threshold: 5`; `reset_timeout_s: 30`; `"on": [unavailable]` |
| `spec.budget` | `max_llm_calls: 50`; `max_tool_calls: 100` |

```bash
mas-ctl chat agent.yaml \
  -o pkg://mas.library.standard/overlays/with-hardened.yaml \
  -o pkg://mas.library.standard/overlays/observability-native.yaml
```

---

## Failure classes

| Class | Meaning | Infra default | Ingress default |
|-------|---------|---------------|-----------------|
| `transient` | Peer answered or the socket dropped; a second identical call may work (429, 5xx including 500, timeout, reset). | LLM retries; tools retry only if idempotent | `allow` (`retry` on `with-hardened`) |
| `unavailable` | Peer is not there (connect refused, DNS, missing provider, open circuit). | LLM and tools retry (LLM POST is treated as idempotent) | `allow` (`retry` on `with-hardened`) |
| `application` | Call ran and returned a domain error (4xx body, tool `ValueError`, unknown tool name). | Never retried | `allow` (store in WM) |
| `fatal` | Will not heal without a config change (TLS verify, 401/403). | Never retried | `block` |

Declare a tool as down with `ExplicitToolUnavailableError` if the provider
should trip the breaker.

---

## Spec knobs

### `spec.control.retry.llm` / `.tools`

| Field | Type | LLM default | Tools default |
|-------|------|-------------|----------------|
| `max_attempts` | integer ≥ 1 | `4` | `2` |
| `backoff_s` | number ≥ 0 | `0.5` | `0.5` |
| `backoff_multiplier` | number ≥ 1 | `2.0` | `2.0` |
| `jitter` | boolean | `true` | `true` |
| `retry_on` | list of failure classes | `[transient, unavailable]` | `[transient, unavailable]` |
| `require_idempotent` | boolean | `false` | `true` |
| `max_backoff_s` | number ≥ 0 or omit | unlimited | unlimited |

`spec.control.retry.llm` overrides infra `LLMProxy.spec.proxy.retry` when
both are set.

### `spec.control.circuit_breaker`

Omit the key (or set `null`) to leave the breaker off. Presence loads the
library plugin (`type: circuit_breaker`, default `threshold`) — not a
kernel op and not a governance plugin.
Card: [circuit-breaker.md](../../library-standard/src/mas/library/standard/plugins/reliability/circuit-breaker.md).

| Field | Type | Default when present |
|-------|------|----------------------|
| `plugin` | string | `threshold` |
| `enabled` | boolean | `true` |
| `failure_threshold` | integer ≥ 1 | `5` |
| `reset_timeout_s` | number ≥ 0 | `30` |
| `"on"` | list of failure classes | `[unavailable]` — **quote the key** in YAML; bare `on` is boolean true |

### `spec.governance[].error_policy` + `error_recovery_plugin`

YAML fields flattened from any plugin stanza. The named plugin is
installed on the ingress chain; the kernel only applies
`GovernanceAction`. Chain semantics:
[governance.md](../manifests/governance.md).

| Field | Values | Default |
|-------|--------|---------|
| `error_policy.transient` | `allow` `retry` `block` `skip` | `allow` |
| `error_policy.unavailable` | same | `allow` |
| `error_policy.application` | same | `allow` |
| `error_policy.fatal` | same | `block` |
| `error_recovery_plugin` | plugin id | unset — ingress follows `gov_ingress_profile` |

Ingress `retry` re-issues the scheduled LLM or tool call up to
`max_gov_retries` (default 2).

### Environment (last resort)

| Variable | Effect |
|----------|--------|
| `MAS_LLM_HTTP_RETRIES` | Extra LLM HTTP retries (`attempts = retries + 1`). Default `3`. |
| `MAS_LLM_HTTP_RETRY_BACKOFF` | Base backoff seconds; also disables jitter. |

Do not put these in `.env` profiles — they apply to every process, including
the controller. Prefer `spec.control.retry.llm`. See [user-config.md](../user-config.md).

---

## Logging

Logger name: **`mas.runtime.reliability`**. Filter JSON logs on
`mas.reliability=true`.

| Outcome (`mas.outcome`) | Level | When |
|-------------------------|-------|------|
| `retry` | WARNING | Infra will sleep and re-issue the same call |
| `recovered` | INFO | Call succeeded after at least one retry |
| `no_retry` | WARNING | Classified failure that the policy will not retry |
| `exhausted` | ERROR | Retry budget spent |
| `circuit_open` / `circuit_half_open` / `circuit_closed` | WARNING / INFO | Breaker state change |
| `llm_error` | ERROR | Engine returns `ERROR` after provider retries |
| `ingress_retry` / `ingress_block` / `ingress_skip` | WARNING / ERROR | Ingress `error_policy` decision |

Each record also carries `mas.target`, `mas.failure_class`,
`mas.failure_code`, `mas.attempt`, `mas.max_attempts`, `mas.delay_s`
when they apply.

Native `events.jsonl` `governance_decision` rows for ingress include
`failure_class`, `failure_code`, and `retry_attempts` when the engine
set them. Infra re-attempts are logs only (they happen inside the HTTP
client, before `_end`).

---

## Composing a flavour (OpenClaw-style)

A flavour is a **deployment preset**, not a dump of every agent plugin.
Behaviour that changes the trajectory belongs on Agent `governance[]` and
`control`, usually via overlays you stack —
[governance.md](../manifests/governance.md),
[flavour.md](../manifests/flavour.md).

| Concern | Overlay / plugin | Notes |
|---------|------------------|--------|
| Undeclared tools | `with-hardened` → `gov_no_undeclared_tool` | Egress chain BLOCK |
| Typed retry / breaker | `with-hardened` → `retry_on_error` + `control.retry` + `circuit_breaker` | Infra then ingress |
| Native traces | `observability-native` | Sequence, not chain |
| Checkpoints / resume | future overlay | Compose; do not fold into the flavour YAML |
| Backtrack on application errors | future `error_policy.application` or a dedicated plugin | Mainline today is `allow` (WM) |
| HITL | `sample_governance` stanza on the chain | Flavour should not own HITL |

---

## Example

```yaml
spec:
  tools:
    - name: get_metrics
      idempotent: true
  governance:
    - gov_no_undeclared_tool
    - retry_on_error:
        error_recovery_plugin: retry_on_error
        error_policy:
          transient: retry
          unavailable: retry
          application: allow
          fatal: block
  control:
    retry:
      llm:
        max_attempts: 4
        retry_on: [transient, unavailable]
      tools:
        max_attempts: 2
        retry_on: [transient, unavailable]
        require_idempotent: true
    circuit_breaker:
      failure_threshold: 5
      reset_timeout_s: 30
      "on": [unavailable]
```
