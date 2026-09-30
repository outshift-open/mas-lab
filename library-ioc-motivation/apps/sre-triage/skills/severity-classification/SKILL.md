---
name: severity-classification
description: >
  SEV1/SEV2/SEV3 classification criteria and escalation paths for production
  incidents. Use this to determine the correct severity level and response
  time based on revenue impact, error rates, and latency thresholds.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [severity, classification, escalation]
---

# Severity Classification

| Level | Criteria | Response Time | Lead |
|-------|----------|---------------|------|
| SEV1  | Revenue-impacting, >20% conversion drop, full outage | Immediate | SRE Lead + VP Eng |
| SEV2  | Degraded service, <20% conversion drop, single region | < 15 min | SRE Lead |
| SEV3  | Intermittent errors, <5% impact, no revenue loss | < 60 min | On-call |

## Checkout / Payment Escalation
- P99 > 2s and conversion drop > 10% → **SEV1**.
- P99 > 1s steady for 5 min → **SEV2**.

## Escalation Path
1. On-call SRE (immediate)
2. SRE Lead (SEV1/SEV2)
3. VP Engineering (SEV1 > 30 min unresolved)
4. CEO/Comms (SEV1 > 60 min or press-worthy)
