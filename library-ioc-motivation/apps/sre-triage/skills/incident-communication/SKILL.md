---
name: incident-communication
description: >
  Incident communication templates for the comms agent. Use this to draft
  status-page messages, internal War Room updates, and resolution notices.
  Covers tone rules, next-update commitments, and escalation language.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [communication, status-page, comms]
---

# Incident Communication Templates

## Initial Status Page Message (within 5 min of SEV1)

> **Investigating — Checkout Degradation**
> We are investigating reports of elevated latency and errors during checkout.
> Some customers may experience slow or failed payments.
> Our team is actively investigating. Next update in 10 minutes.

## Progress Update (every 10–15 min)

> **Update — Checkout Degradation [HH:MM UTC]**
> Our team has identified [X] as a contributing factor and is implementing a mitigation.
> Affected service: Checkout / Payment processing.
> Customer impact: [describe impact level].
> Next update in 10 minutes.

## Resolution Message

> **Resolved — Checkout Degradation [HH:MM UTC]**
> The issue affecting checkout has been resolved. [Brief description of root cause and fix.]
> All services are operating normally. We apologize for the inconvenience.
> A postmortem will be published within 48 hours.

## Internal War Room Message

> @here SEV1 active — Checkout latency spike + 40% conversion drop.
> War Room: #incident-sev1-payments
> IC: [Name]
> Bridge: [Link]
> Current status: [investigating / mitigating / resolved]

## Communication Rules

- Never speculate about root cause in public messages — say "investigating" until confirmed.
- Always provide a next-update time.
- Use customer-impact language, not technical jargon.
- Coordinate with SRE Lead before posting any root-cause information publicly.
