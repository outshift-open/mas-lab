#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""JSON Schema envelope validation for OTel SDK span JSONL lines.

Validates the *wire shape* of each span (``name``, ``context``, timestamps,
``attributes`` bag) against ``schemas/otel_sdk_spans.schema.json``.  The MAS
*semantics* (per-``span.name`` ``mas.*`` attributes) are validated separately by
:class:`mas.library.telemetry.verification.spanspec.SpanValidator`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_BUILTIN_JSON_SCHEMA = (
    Path(__file__).resolve().parent.parent / "schemas" / "otel_sdk_spans.schema.json"
)


def validate_span_json_schema(
    span: Dict[str, Any], schema: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Validate one span dict against the bundled JSON Schema envelope.

    Returns a list of human-readable error strings (empty when valid).  Returns
    ``[]`` when ``jsonschema`` is not installed (validation is best-effort).
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return []

    if schema is None:
        if not _BUILTIN_JSON_SCHEMA.exists():
            return [f"json_schema_missing: {_BUILTIN_JSON_SCHEMA}"]
        schema = json.loads(_BUILTIN_JSON_SCHEMA.read_text(encoding="utf-8"))

    errors: List[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(span), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{path}: {err.message}")
    return errors


def validate_spans_json_schema(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate all spans against the bundled JSON Schema; return a report dict."""
    per_span: List[Dict[str, Any]] = []
    total_errors = 0
    for i, span in enumerate(spans):
        errs = validate_span_json_schema(span)
        if errs:
            per_span.append({"index": i, "name": span.get("name", ""), "errors": errs})
            total_errors += len(errs)
    return {
        "ok": total_errors == 0,
        "schema_file": str(_BUILTIN_JSON_SCHEMA),
        "total_spans": len(spans),
        "error_count": total_errors,
        "span_errors": per_span[:20],
    }


__all__ = ["validate_span_json_schema", "validate_spans_json_schema"]
