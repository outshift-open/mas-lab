# library-kg schemas — native events.jsonl

Two-layer validation (same architecture as OTel in `library-telemetry`):

| Layer | File | Role |
|-------|------|------|
| **Envelope (L1–L2)** | [`events.schema.json`](events.schema.json) | JSON types, `kind` enum, `call_id` on `*_start`/`*_end` |
| **Semantics (L3)** | [`events.spec.yaml`](events.spec.yaml) | Per-kind required/recommended payload fields |

**Tools:** `EventValidator`, `verify_events_file()` in `mas.library.kg.observability.native`.

**Pipeline:** `verify_events` step in `mas-lab-graph` (before `normalize_events`).

Regenerate JSON Schema after `_KIND_TO_CLASS` changes:

```bash
cd library-kg && python scripts/generate_events_schema.py
```

**OTel note:** `otel_sdk_spans.schema.json` + `mas.spanspec.yaml` are intentionally separate —
JSON Schema checks wire format; SpanSpec checks per-span semantics. Merging them would mix
syntax and meaning. Native events use the same split.

**Prose:** `papers/mas-ontology-kg/appendices/R-mealy-observability-contract.md`
