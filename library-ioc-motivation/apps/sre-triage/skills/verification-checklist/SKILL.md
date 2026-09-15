---
name: verification-checklist
description: >
  Pre-approval checklist and logical consistency rules for the verifier agent.
  Use this before approving a triage report: verify evidence completeness,
  check that mitigation matches root cause, and identify escalation triggers.
  Returns APPROVED, FLAGGED, or BLOCKED.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [verification, checklist, verifier, approval]
---

# Triage Verification Checklist

## Evidence Completeness

Before approving a final triage report, verify:

- [ ] Telemetry agent confirmed which service/span is slow (internal vs external)
- [ ] Backend agent confirmed or ruled out a recent deployment as root cause
- [ ] DB agent confirmed or ruled out database contention
- [ ] At least one concrete metric value justifies the root cause conclusion
- [ ] Proposed mitigation is proportional to the confirmed root cause

## Logical Consistency Rules

1. **Root cause must match evidence**: If the conclusion is "DB contention" but DB latency metrics show normal values, flag as inconsistent.
2. **Mitigation must target root cause**: If root cause is "external gateway timeout", rolling back a recent deploy is not the right fix — flag it.
3. **Risk must be acknowledged**: Any mitigation that could cause data loss or extended downtime must be explicitly flagged.

## Escalation Triggers

Flag these issues immediately to the SRE Lead:
- Proposed action involves schema change or data deletion.
- Evidence is contradictory between agents.
- Incident has been active > 30 min with no confirmed root cause.
- Any agent suggests a mitigation not in the approved playbook.

## Verification Output Format

Report back:
- **APPROVED** — evidence supports conclusion, mitigation is safe.
- **FLAGGED** — specific inconsistency or risk identified (describe it).
- **BLOCKED** — critical safety concern, do not proceed (describe it).
