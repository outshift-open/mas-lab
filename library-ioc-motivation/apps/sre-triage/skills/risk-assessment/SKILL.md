---
name: risk-assessment
description: >
  Risk classification and approval level table for incident remediation
  actions. Use this when evaluating whether a proposed action is LOW,
  MEDIUM, HIGH, or CRITICAL risk and who must approve it. Includes
  evidence standards required before approving high-risk actions.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [risk, assessment, verifier, approval]
---

# Risk Assessment for Incident Actions

## Risk Classification

| Risk Level | Definition | Approval Required |
|-----------|-----------|------------------|
| LOW | Reversible, no data impact, isolated to one service | On-call SRE |
| MEDIUM | May impact multiple services, reversible with effort | SRE Lead |
| HIGH | Potential data loss, extended downtime, irreversible | VP Engineering |
| CRITICAL | Data corruption, security breach, compliance violation | CEO + Legal |

## Action Risk Table

| Action | Risk Level | Notes |
|--------|-----------|-------|
| Kill slow query | LOW | Reversible, may retry |
| Feature flag disable | LOW | Instant rollback available |
| Service rollback | LOW | Provided tests pass |
| Scale out pods | LOW | Cost impact only |
| Kill all connections | MEDIUM | Brief service blip |
| Disable payment method | MEDIUM | Revenue impact, user-visible |
| Restart payment service | MEDIUM | Brief downtime |
| Schema migration | HIGH | Irreversible, needs downtime |
| Drop table or index | CRITICAL | Data loss, FORBIDDEN during incident |

## Evidence Standards

For a recommendation to be actionable, it must be supported by:
- At least one quantitative metric (not just log messages)
- Clear temporal correlation (issue started after event X)
- No contradicting evidence from other agents

## Checklist Before Approving High-Risk Actions

- [ ] Root cause confirmed by ≥ 2 independent signals
- [ ] Rollback plan documented
- [ ] Customer impact of action estimated
- [ ] SRE Lead notified
