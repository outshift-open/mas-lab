---
name: latency-analysis
description: >
  P99 spike investigation process for the telemetry analyst. Use this to
  systematically isolate latency spikes by span type, error correlation,
  traffic analysis, and deployment comparison. Applies to any service
  showing elevated P99 or P95 latency.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [latency, telemetry, analysis]
---

# Latency Analysis

## P99 Spike Investigation Process

1. **Isolate the spike boundary** — compare P50 vs P99. If P50 is stable and P99 spikes, the issue is in the long tail (timeouts, lock waits, retries).

2. **Decompose by span type**:
   - `db.*` spans slow → database contention
   - `http.client.*` spans slow → external service (payment gateway, 3rd-party API)
   - `app.*` spans slow → CPU-bound or thread starvation

3. **Check error rates alongside latency** — latency spike with errors → hard failures (connection refused, timeouts). Latency spike without errors → soft slowdown (capacity, GC, lock waits).

4. **Traffic analysis**:
   - Spike in request volume? → Overload scenario.
   - Normal traffic but latency up? → Resource contention or downstream issue.

5. **Compare pre/post deployment windows** — if a deploy happened in the last 60 min, compare baseline P99 before vs after.

## OTel Signals to Query
- `{service}` trace duration histogram (P50, P95, P99)
- `{service} -> {service}_db` span durations (DB layer)
- `{service} -> payment_gateway` span durations (or equivalent upstream)
- Error count by status code (HTTP 500, 503, 504)
- Compare `{service}` baseline (pre-incident) vs current window
