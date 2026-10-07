#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Standalone step: verify an ``otel_sdk_spans.jsonl`` file (structural + SpanSpec)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def run_verify_spans(
    spans_path: str | Path,
    *,
    spanspec_level: str = "L3",
    spanspec_path: Optional[str] = None,
    spanspec_strictness: str = "required",
    fail_on_error: bool = False,
) -> Dict[str, Any]:
    """Run structural + JSON-schema + SpanSpec verification on a spans file.

    Returns the combined report dict (see
    :func:`mas.library.telemetry.verification.structural.verify_otel_file`), with
    an ``error_count`` convenience key added.
    """
    from mas.library.telemetry.verification.structural import verify_otel_file

    spans_path = Path(spans_path).expanduser().resolve()
    report = verify_otel_file(
        spans_path,
        spanspec_level=spanspec_level,
        spanspec_path=spanspec_path,
        spanspec_fail_on_error=fail_on_error,
        spanspec_strictness=spanspec_strictness,
    )
    report["error_count"] = len(report.get("errors", []))
    if fail_on_error and not report.get("ok", False):
        logger.error(
            "verify_spans: %d error(s) in %s", report["error_count"], spans_path
        )
    return report


__all__ = ["run_verify_spans"]
