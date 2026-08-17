---
name: otel-correlation
description: >
  OpenTelemetry trace correlation guide for finding slow spans, detecting
  cascades, and distinguishing internal vs external root causes. Use this
  to interpret get_service_health, get_metrics, and get_logs results and
  determine whether latency is app-internal or from a downstream dependency.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [otel, telemetry, tracing, correlation]
---

# OTel Trace Correlation

## Finding the Slow Span

1. Call `get_service_health(service="{service}")` first to get a high-level status overview.
2. Call `get_metrics(service="{service}", metric="latency_p99", window="15m")` for quantitative data.
3. Call `get_logs(service="{service}", level="ERROR", limit=15)` to identify error chains.
4. Call `get_metrics(service="{service}")` (without metric param) for the full metrics snapshot.

## Reading the Results

- If `upstream_latency > 80%` of total span → external dependency (gateway or DB)
- If `internal_latency > 80%` → CPU, thread pool, or in-process serialization issue
- If error rate > 1% with timeout errors in logs → external call timing out (not DB lock)
- `error_rate > 0.20` with `p99 > 4000ms` → critical SLO breach, likely total dependency failure

## Cascade Detection

Look for: service A slow → service B slow, with timing overlap suggesting a cascade.

Cascade pattern: app service P99 spike starts **before** DB spike → application-level issue (e.g., async client timeout misconfiguration).
DB spike starts **before** app service spike → DB root cause.

## Reporting Format

Report back with:
- Confirmed slow span(s) and their duration
- Whether the cause is internal or external
- Error rate and type breakdown
- Deployment overlap if any
