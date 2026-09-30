---
name: deployment-investigation-no-logs
description: >
  Checklist for evaluating whether a recent deployment caused the active
  incident, WITHOUT access to log data. Use this when a deploy occurred in the
  last 60 minutes or when the root cause is unclear. Covers rollback decision
  criteria and config change audit only — log correlation is unavailable.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [deployment, rollback, backend]
---

# Deployment Investigation (no logs)

You do NOT have access to the `get_logs` tool. Investigate deployments from
deployment and telemetry evidence alone; do not attempt to correlate against
error logs.

## Checklist

1. Call `get_deployments(service="{service}", window="60m")` to list recent deploys.
2. If a deployment exists in the last 30 minutes:
   - Note the commit SHA, commit message, and `overlap_with_incident` flag.
   - Cross-reference with P99 spike start time in telemetry data.
   - Recommend rollback immediately if deploy overlaps with incident window.

## Rollback Decision Tree

- Deploy < 30 min ago AND P99 spike started within 5 min of deploy → **ROLLBACK NOW**.
- Deploy > 30 min ago → likely not the cause; continue investigation.
- No recent deploy → eliminate as root cause, focus on DB / external.

## Config Changes

Check for:
- Async/blocking model changes in network or DB clients
- Feature flag changes (enabledGateway, enabledRateLimit)
- Environment variable changes (POOL_SIZE, TIMEOUT_MS, CONNECT_TIMEOUT)
- Infrastructure scaling events (autoscaler changes)

## Reporting Format

Report back:
- Last deployment: SHA, time, author, commit message
- Deployment overlap assessment (yes/no, with `overlap_with_incident` field)
- Rollback recommendation with service + version if applicable
