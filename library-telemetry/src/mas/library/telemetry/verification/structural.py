#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Structural span checks + the combined ``verify_otel_file`` entry point.

Three complementary layers of verification, mirroring ``library-kg``'s combined
KG validation:

1. **structural** — required fields, a root span, MAS boundary presence, single
   trace (:func:`verify_otel_spans`);
2. **JSON schema envelope** — wire shape
   (:func:`mas.library.telemetry.verification.schema.validate_spans_json_schema`);
3. **SpanSpec L1–L4** — MAS semantics
   (:class:`mas.library.telemetry.verification.spanspec.SpanValidator`).

:func:`verify_otel_file` runs all three against a JSONL file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from mas.library.telemetry.verification.schema import validate_spans_json_schema
from mas.library.telemetry.verification.spanspec import SpanValidator


def verify_otel_spans(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run structural checks on OTel SDK span dicts.

    Returns ``{"ok", "errors", "warnings", "stats"}``.
    """
    errors: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, Any] = {"total_spans": len(spans)}

    if not spans:
        errors.append("file_not_empty: no spans found")
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats}

    required_span_fields = ["name", "start_time", "end_time"]
    required_ctx_fields = ["span_id", "trace_id"]
    bad_spans: List[str] = []
    for i, s in enumerate(spans):
        missing = [f for f in required_span_fields if not s.get(f)]
        ctx = s.get("context") or {}
        missing += [f"context.{f}" for f in required_ctx_fields if not ctx.get(f)]
        if missing:
            bad_spans.append(f"span[{i}] ({s.get('name', '?')}): missing {missing}")
    if bad_spans:
        errors.append(f"required_fields: {len(bad_spans)} span(s) missing fields")
        errors.extend(f"  {b}" for b in bad_spans[:5])

    mas_spans = [s for s in spans if s.get("attributes", {}).get("mas.boundary")]
    stats["mas_spans"] = len(mas_spans)
    if not mas_spans:
        warnings.append(
            "mas_boundary_present: no span has 'mas.boundary' attribute "
            "— trace may not be a MAS trace"
        )

    roots = [s for s in spans if not s.get("parent_id")]
    stats["root_spans"] = len(roots)
    if not roots:
        errors.append(
            "root_span_present: no root span found — all spans have parent_id"
        )

    trace_ids = {
        (s.get("context") or {}).get("trace_id")
        for s in spans
        if (s.get("context") or {}).get("trace_id")
    }
    stats["trace_ids"] = len(trace_ids)
    if len(trace_ids) > 1:
        warnings.append(
            f"single_trace: {len(trace_ids)} distinct trace_ids — "
            "dump may contain multiple runs; normalize will deduplicate"
        )

    stats["agents"] = sorted(
        {
            s.get("attributes", {}).get("mas.agent.id", "")
            for s in spans
            if s.get("attributes", {}).get("mas.agent.id")
        }
    )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def verify_otel_file(
    path: Union[str, Path],
    *,
    spanspec_level: str = "L3",
    spanspec_path: Optional[str] = None,
    spanspec_fail_on_error: bool = False,
    spanspec_strictness: str = "required",
) -> Dict[str, Any]:
    """Load a JSONL file and run structural + JSON-schema + SpanSpec verification."""
    src = Path(path)
    spans: List[Dict[str, Any]] = []
    with src.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                spans.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{src}:{lineno}: invalid JSON: {exc}") from exc

    report = verify_otel_spans(spans)
    report["file"] = str(src)

    schema_report = validate_spans_json_schema(spans)
    report["json_schema"] = schema_report
    schema_errors: List[str] = []
    if not schema_report.get("ok"):
        schema_errors.append(
            f"json_schema: {schema_report.get('error_count', 0)} error(s)"
        )
        for item in schema_report.get("span_errors", [])[:5]:
            schema_errors.append(
                f"  span[{item.get('index')}] ({item.get('name')}): "
                + "; ".join(item.get("errors", [])[:3])
            )

    spanspec_errors: List[str] = []
    strictness = (
        spanspec_strictness
        if spanspec_strictness in {"required", "recommended", "complete"}
        else "required"
    )
    spec_path = spanspec_path
    if not spec_path and SpanValidator.looks_like_observe_sdk(spans):
        from mas.library.telemetry.verification.spanspec import _OBSERVE_SDK_SPEC

        if _OBSERVE_SDK_SPEC.exists():
            spec_path = str(_OBSERVE_SDK_SPEC)
    validator = SpanValidator(spec_path) if spec_path else SpanValidator()
    declared = validator.declared_levels()
    level = spanspec_level
    if declared and spanspec_level not in declared:
        for candidate in ("L2", "L3", "L1", "L0", "L4"):
            if candidate in declared:
                level = candidate
                break
    spec_report = validator.validate(spans, strictness=strictness)  # type: ignore[arg-type]
    report["spanspec"] = spec_report.summary()
    report["spanspec"]["level_checked"] = level
    report["spanspec"]["strictness"] = strictness
    report["spanspec"]["conformance_at_level"] = spec_report.conformance(level)
    level_errors = spec_report.errors(level)
    if level_errors:
        spanspec_errors.append(
            f"spanspec_{level}: {len(level_errors)} error(s)"
        )
        for v in level_errors[:5]:
            spanspec_errors.append(
                f"  {v.span_name}: {v.message}"
                + (f" ({v.attribute})" if v.attribute else "")
            )

    if schema_errors:
        report["errors"].extend(schema_errors)
        report["ok"] = False
    if spanspec_errors and spanspec_fail_on_error:
        report["errors"].extend(spanspec_errors)
        report["ok"] = False

    return report


__all__ = ["verify_otel_spans", "verify_otel_file"]
