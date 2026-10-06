#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OTel span verification — the analogue of ``library-kg``'s KG verifier.

Three complementary layers plus structural span comparison:

SpanSpec (L1–L4 semantics)
--------------------------
``SpanValidator``               — validate spans against a ``.spanspec.yaml``
``ValidationReport`` / ``Violation`` — report types
``StrictnessMode``              — ``required`` / ``recommended`` / ``complete``
``load_spans``                  — load OTel SDK spans from JSONL

JSON Schema envelope (wire shape)
---------------------------------
``validate_span_json_schema``   — one span → error strings
``validate_spans_json_schema``  — all spans → report dict

Structural + combined
----------------------
``verify_otel_spans``           — required fields / root / boundary / single trace
``verify_otel_file``            — structural + JSON schema + SpanSpec, from a file

Span parity comparison
----------------------
``compare_otel_span_sets``      — compare two in-memory span lists
``compare_otel_span_files``     — compare two JSONL files
``compare_otel_span_files_multi`` — one reference vs many candidates
"""

from mas.library.telemetry.verification.compare import (
    compare_otel_span_files,
    compare_otel_span_files_multi,
    compare_otel_span_sets,
)
from mas.library.telemetry.verification.schema import (
    validate_span_json_schema,
    validate_spans_json_schema,
)
from mas.library.telemetry.verification.spanspec import (
    StrictnessMode,
    SpanValidator,
    ValidationReport,
    Violation,
    load_spans,
)
from mas.library.telemetry.verification.structural import (
    verify_otel_file,
    verify_otel_spans,
)

__all__ = [
    # spanspec
    "SpanValidator",
    "ValidationReport",
    "Violation",
    "StrictnessMode",
    "load_spans",
    # json schema
    "validate_span_json_schema",
    "validate_spans_json_schema",
    # structural + combined
    "verify_otel_spans",
    "verify_otel_file",
    # compare
    "compare_otel_span_sets",
    "compare_otel_span_files",
    "compare_otel_span_files_multi",
]
