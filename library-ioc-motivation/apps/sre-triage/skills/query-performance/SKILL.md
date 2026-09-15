---
name: query-performance
description: >
  Database query performance investigation for the DB specialist. Use this
  when query_latency_p99 exceeds 500ms, slow query count is high, or
  active connections approach the maximum. Covers slow query patterns,
  emergency mitigations, and index recommendations.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [query, performance, database, db]
---

# Query Performance Investigation

## Investigation Steps

1. Call `get_metrics(service="payment_db", metric="query_latency_p99", window="15m")`.
2. Call `get_metrics(service="payment_db", metric="active_connections", window="15m")`.
3. Call `get_metrics(service="payment_db", metric="slow_queries", window="15m")`.

## Interpreting Results

- `query_latency_p99 > 500ms` → slow query problem, check indexes and execution plans.
- `active_connections > 80% of max_connections` → connection saturation.
- `slow_queries count > 10/min` → missing index or full table scan.

## Common Slow Query Patterns

| Pattern | Symptom | Fix |
|---------|---------|-----|
| Missing index on `transactions` | Full table scan on writes | Add index (after incident) |
| Unparameterized queries | Plan cache misses | Code fix |
| N+1 query cascade | High query count, low individual latency | ORM fix |
| Batch inserts without lock | Lock escalation | Use row-level locking |

## Emergency Mitigations (during incident)

- Kill long-running queries via `run_action(action="kill_slow_queries")`.
- Reduce connection pool size on application side to prevent pileup.
- Enable read replica routing for non-write queries if available.

## Reporting Format

- Current P99 query latency
- Slow query count / type
- Whether kill action was taken
- Index recommendation for postmortem
