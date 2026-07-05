#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.lab.telemetry — re-exports from mas-lab-telemetry when installed."""

_INTERNAL_MSG = "requires mas-lab-telemetry (internal)"


def _internal_only(name: str):
    def _stub(*_args, **_kwargs):
        raise ImportError(f"{name} {_INTERNAL_MSG}")

    _stub.__name__ = name
    return _stub


try:
    from mas.internal.telemetry.otlp_push import load_events, push_file
    from mas.internal.telemetry.validate import SpanValidator
    from mas.internal.telemetry.verify import verify_otel_file, verify_otel_spans
    from mas.internal.telemetry.compare import (
        compare_otel_span_files,
        compare_otel_span_files_multi,
        compare_otel_span_sets,
    )

    __all__ = [
        "push_file",
        "load_events",
        "SpanValidator",
        "verify_otel_spans",
        "verify_otel_file",
        "compare_otel_span_sets",
        "compare_otel_span_files",
        "compare_otel_span_files_multi",
    ]
except ImportError:
    from ._otlp_push_impl import load_events, push_file

    SpanValidator = _internal_only("SpanValidator")  # type: ignore[misc,assignment]
    verify_otel_spans = _internal_only("verify_otel_spans")
    verify_otel_file = _internal_only("verify_otel_file")
    compare_otel_span_sets = _internal_only("compare_otel_span_sets")
    compare_otel_span_files = _internal_only("compare_otel_span_files")
    compare_otel_span_files_multi = _internal_only("compare_otel_span_files_multi")

    __all__ = [
        "push_file",
        "load_events",
        "SpanValidator",
        "verify_otel_spans",
        "verify_otel_file",
        "compare_otel_span_sets",
        "compare_otel_span_files",
        "compare_otel_span_files_multi",
    ]
