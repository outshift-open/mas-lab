---
name: data-access-protocol
description: >
  Tool invocation discipline for all data-access tools (get_metrics, get_logs,
  get_service_health, get_deployments, query_db). Use this to ensure every tool
  call uses the exact canonical service name from the incident description.
  Prevents tool errors and cross-agent correlation failures.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [data-access, protocol, shared]
---

# Data Access Protocol

## Tool Invocation Discipline

When calling any data tool (`get_metrics`, `get_logs`, `get_service_health`,
`get_deployments`, `query_db`), you MUST pass the canonical service name as
the `service` argument.

**Rule**: Use the **exact** service identifier from the incident description
verbatim (e.g. `"payment-service"`). Do not omit the `service` argument, do
not paraphrase the name, and do not substitute a generic placeholder.

**Why this matters**: Omitting or misspelling the service name causes tools
to return an error — there is no default fallback. Agents will see
`"error": "required parameter 'service' is missing"` if the argument is
absent. Cross-agent correlation fails when different agents query different
service names for the same incident.

## Correct Pattern

```
get_metrics(service="payment-service")   # ✓ exact canonical name
get_logs(service="payment-service")      # ✓ same canonical name
get_deployments(service="payment-service")  # ✓ consistent
```

## Incorrect Patterns

```
get_metrics()                   # ✗ missing service arg → tool returns error
get_metrics(service="payment")  # ✗ partial name → tool returns error
get_metrics(service="service")  # ✗ generic placeholder → tool returns error
```

## Where to Find the Canonical Name

The canonical service name appears in:
- The incident fixture: `spec.params.incident_fixture` → `services:` keys
- The SRE's initial incident description passed to you at delegation time
- The incident summary in your system context

Use it verbatim. Do not normalise underscores to hyphens or vice versa unless
the fixture explicitly lists both as aliases.
