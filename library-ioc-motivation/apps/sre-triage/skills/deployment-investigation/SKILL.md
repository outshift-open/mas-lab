---
name: deployment-investigation
description: >
  Checklist for evaluating whether a recent deployment caused the active
  incident. Use this when a deploy occurred in the last 60 minutes or when
  the root cause is unclear. Covers rollback decision criteria, config change
  audit, and log correlation.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [deployment, rollback, backend]
---

# Deployment Investigation

## Checklist

1. Call `get_deployments(service="{service}", window="60m")` to list recent deploys.
2. If a deployment exists in the last 30 minutes:
   - Note the commit SHA, commit message, and `overlap_with_incident` flag.
   - Cross-reference with P99 spike start time in telemetry data.
   - Recommend rollback immediately if deploy overlaps with incident window.
3. Call `get_logs(service="{service}", level="ERROR", limit=15)` to find error patterns linked to the deploy.

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
- Log evidence corroborating (or ruling out) the deploy as root cause
- Rollback recommendation with service + version if applicable
