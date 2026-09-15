---
name: slo-framing
description: >
  SLO breach framing rules for incident communications. Use this to decide
  when and how to mention SLO breaches in public vs internal messages,
  translate technical SLO language to customer-impact language, and
  determine escalation thresholds based on incident duration.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [slo, framing, comms, escalation]
---

# SLO Framing for Incident Communications

## SLO Definitions (Payment Service)

| SLO | Target | Current Status |
|-----|--------|---------------|
| Checkout availability | 99.9% | Check from metrics |
| Payment P99 latency | < 500ms | Breached at 4.2s |
| Checkout conversion rate | Baseline -5% max | Breached at -40% |

## When to Mention SLO Breach

- Public status page: **Do NOT** mention SLO breach explicitly. Use customer impact language.
- Internal update: **DO** state "SLO breach: checkout P99 4.2s vs 500ms target."
- Post-incident report: **Always** include SLO breach duration and error budget impact.

## Error Budget Language

Instead of: "We are in breach of our SLA."
Write: "Users are experiencing response times significantly above our performance target."

Instead of: "SLA violation for enterprise customers."
Write: "Business-critical checkout flows are experiencing degraded performance."

## Escalation Criteria

| Condition | Action |
|-----------|--------|
| SEV1 > 30 min unresolved | Notify VP Engineering |
| SEV1 > 60 min unresolved | Notify CEO + PR team |
| Payment data loss suspected | Legal + Security team immediately |

## Metrics to Include in Updates

Use `get_metrics` to retrieve current:
- Checkout conversion rate (vs baseline)
- Payment P99 latency
- Error rate on payment endpoint
