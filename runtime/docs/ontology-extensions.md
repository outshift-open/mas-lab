<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Ontology extensions

Semantic annotations for traces, governance events, and manifest overlays.

---

## Purpose

MAS Lab traces are consumed by bench pipelines (MCE, lifecycle figures, Mealy
stats). Ontology fields make events **machine-interpretable** without scraping
free text.

---

## Event payload extensions

Common extension keys in `events.jsonl`:

| Key | Used by |
|-----|---------|
| `symbol` | Envelope activity (`EnvelopeSymbol` value) |
| `segment_id` | Context provenance linkage |
| `policy_name` | Governance decision attribution |
| `dp_phase` | Design-pattern phase (plan/act/synth) |
| `scheduled_op` | `LLM_CALL`, `TOOL_CALL`, … |

Pipeline steps `extract_trace_stats` and `extract_mealy_stats` read these fields.

---

## Manifest overlays

Overlays may attach semantic tags:

```yaml
metadata:
  labels:
    mas.lab/scenario: baseline
    mas.lab/paper-figure: fig-3
```

Labels are copied into run metadata for experiment grouping.

---

## Lab-specific vocabularies

Paper labs may define local enums under `lib/` (e.g. lifecycle-control moodbar
states). Keep lab vocabularies **inside the lab**; do not extend global event
kinds without a schema bump in `trajectory-schema.md`.

---

## Related docs

- [trajectory-schema.md](trajectory-schema.md)
- [semantic-protocols.md](semantic-protocols.md)
- [context-segmentation.md](context-segmentation.md)
