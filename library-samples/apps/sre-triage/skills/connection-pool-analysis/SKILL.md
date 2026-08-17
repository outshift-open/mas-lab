---
name: connection-pool-analysis
description: >
  Diagnosis guide for database connection pool exhaustion in backend services.
  Use this when observing request queue buildup, P99 latency increase with
  stable P50, or errors like "connection timeout" / "pool exhausted".
  Covers investigation steps, root causes, and mitigations.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [connection-pool, backend, database]
---

# Connection Pool Analysis

## Symptoms of Pool Exhaustion

- Request queue builds up waiting for a connection.
- P99 latency increases while P50 stays flat (leading edge of pool exhaustion).
- Errors: `connection timeout`, `too many connections`, `pool exhausted`.

## Investigation Steps

1. Call `get_metrics(service="{service}", metric="db_pool_utilization", window="15m")`.
2. Call `get_metrics(service="{service}", metric="db_pool_wait_time", window="15m")`.
3. If utilization > 90%: pool is likely exhausted.
4. Cross-reference with `get_metrics(service="{service}_db", metric="active_connections")` for the DB side.

## Root Causes of Pool Exhaustion

- Long-running transactions holding connections too long.
- Increased traffic without proportional pool scaling.
- Connection leak (connections not returned to pool on error path).
- DB slowdown causing connections to be held longer.

## Mitigations

| Cause | Mitigation |
|-------|-----------|
| Traffic spike | Scale out payment service pods |
| Long transactions | Kill slow transactions (coordinate with DB agent) |
| Connection leak | Rollback or hotfix code |
| DB slow | Coordinate pool_size reduction until DB recovers |

## Reporting Format

- Pool utilization % and wait time P99
- Whether pool exhaustion is confirmed
- Recommended mitigation
