---
name: triage-protocol
description: >
  Step-by-step incident triage protocol for the SRE orchestrator. Use this
  to guide parallel investigation dispatch, root-cause synthesis, mandatory
  verification gate, and final report. Applies to any SEV1/SEV2/SEV3 incident.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [triage, protocol, orchestrator]
---

# Incident Triage Protocol

## Step 1 — Initial Assessment (< 2 minutes)
- Confirm incident symptoms (latency, error rates, conversion impact).
- Check if this is a new event or regression from a known issue.
- Set initial severity (SEV1 / SEV2 / SEV3) based on customer impact.

## Step 2 — Parallel Investigation Delegation
Immediately dispatch tasks to specialist agents:
- **Telemetry Agent**: analyse span/trace latency breakdown, error rates, anomaly correlation.
- **Backend Agent**: check recent deployments, connection pool usage, config changes.
- **DB Agent**: inspect slow queries, lock contention, connection pool saturation.
- **Comms Agent**: draft initial status-page update and internal War Room message.

Do NOT wait for one agent to finish before calling the next. Dispatch all in sequence.

## Step 3 — Collect Findings
Wait for each specialist to return a result, then aggregate.

## Step 4 — Root Cause & Action Plan
Based on collected evidence, identify the most likely root cause and write:
- Confirmed or suspected root cause
- Immediate mitigation (rollback / feature flag / query kill)
- Follow-up actions (monitoring, postmortem)

## Step 5 — Verification Gate (MANDATORY before any remediation action)
Before calling `run_action`, you MUST delegate to the Verifier agent:
- Call `delegate_to_verifier` with your root cause summary and action plan.
- Wait for the Verifier response. It will contain one of:
  - `VERIFICATION: APPROVED` — proceed to Step 6
  - `VERIFICATION: FLAGGED — <reason>` — address the flagged concern, then re-verify
  - `VERIFICATION: REJECTED — <reason>` — do NOT proceed; escalate to incident commander
- **NEVER call `run_action` without a prior `VERIFICATION: APPROVED` in the current session.**

## Step 6 — Final Report
Produce a single consolidated triage report for the incident commander.
Include the verification outcome (e.g. "Verified by Verifier — APPROVED").

## Step 7 — Remediation Action
Only after receiving `VERIFICATION: APPROVED`, call `run_action` with the approved plan.
