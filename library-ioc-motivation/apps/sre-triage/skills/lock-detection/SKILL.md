---
name: lock-detection
description: >
  Lock contention and deadlock analysis for database incidents. Use this
  when observing lock_wait_timeout errors, sudden write queue buildup, or
  P99 spikes on INSERT/UPDATE operations. Covers safe mitigations, risk
  table, and blocking query kill procedure.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [locks, deadlocks, database, db]
---

# Lock Detection & Deadlock Analysis

## Symptoms

- `lock_wait_timeout` errors in application logs.
- Sudden queue buildup on write operations.
- P99 spike on `INSERT`/`UPDATE` to `payments` or `transactions` table.

## Investigation Steps

1. Call `get_metrics(service="{db_service}", metric="lock_wait_count", window="15m")`.
2. Call `get_metrics(service="{db_service}", metric="deadlock_count", window="15m")`.
3. Call `query_db(service="{db_service}", query_type="blocking_queries")` to get live pg_stat_activity data.
4. Call `query_db(service="{db_service}", query_type="pg_stat_activity")` for full connection picture.
5. Call `get_logs(service="{db_service}", level="ERROR", limit=10)` for lock timeout messages.

## Interpreting Results

- `lock_wait_count > 50/min` → active lock contention.
- `deadlock_count > 0` → circular lock dependency, check transaction order in code.
- `blocking_queries` non-empty in `query_db` result → live blocking chain, act immediately.
- `waiting_queries == 0` AND `blocking_queries == []` → DB is **not** root cause, escalate to backend/network.
- Logs showing `Lock wait timeout exceeded` → transactions blocking each other.

## Safe Mitigations During Incident

1. **Kill blocking transactions** — use `run_action(action="kill_blocking_queries")` **only if** `blocking_queries` is non-empty.
2. **Coordinate with Backend Agent** — identify if a recent deploy changed transaction scope or connection handling.
3. **Do NOT drop or truncate tables** — data integrity is paramount.

## Risk Assessment

| Action | Risk Level | Reversible? |
|--------|-----------|------------|
| Kill blocking queries | Low | Yes |
| Rollback transaction | Low | Yes |
| Schema change | CRITICAL | No — defer to postmortem |
| Drop table / index | CRITICAL | No — forbidden during incident |

## Reporting Format

- Lock wait count and deadlock count
- Blocking transaction IDs if available
- Actions taken
- Whether DB is confirmed as root cause
