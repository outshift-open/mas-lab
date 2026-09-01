---
name: incident-triage
description: >
  Orchestrate a multi-agent investigation of a production incident: collect
  telemetry evidence, correlate backend and DB signals, draft stakeholder
  communications, verify the proposed action through the verifier gate, and
  emit a consolidated root-cause analysis with recommended remediation.
  Use when a service is degraded, error rates rise, or conversion drops.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [incident, triage, orchestration, sre]
---

# Incident Triage Skill

This skill enables the SRE orchestrator to run a complete multi-agent
incident triage workflow from initial alert to verified remediation.

## Inputs

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `incident_description` | string | yes | Free-text description of the observed symptom (e.g., latency spike, error rate, service down) |
| `affected_service` | string | no | Name of the impacted service — improves routing if provided |
| `severity` | string | no | P0 (critical), P1 (major), P2 (minor) |

## Outputs

| Field | Type | Description |
|-------|------|-------------|
| `root_cause_analysis` | object | Structured RCA with contributing factors and evidence |
| `action_plan` | array | Ordered list of remediation steps with assigned owners |
| `stakeholder_update` | string | Human-readable comms draft for customer-facing or internal channels |

## Constraints

- All 5 specialist agents (telemetry, backend, db, comms, verifier) must respond before the final report is emitted.
- Remediation actions must be verified by the verifier agent before execution.
- `run_action` must only be called after receiving `VERIFICATION: APPROVED`.

## Taxonomy

`sre` · `incident` · `orchestration`

## Workflow

See [triage-protocol](../triage-protocol/SKILL.md) for the step-by-step
triage procedure that this skill orchestrates.
