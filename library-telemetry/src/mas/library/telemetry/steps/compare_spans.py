#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Standalone step: structural parity comparison of two OTel span files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def run_compare_spans(
    reference_path: str | Path,
    candidate_path: str | Path,
    *,
    strict: bool = True,
    fail_on_error: bool = False,
    output_path: Optional[str | Path] = None,
    reference_label: str = "reference",
    candidate_label: str = "candidate",
) -> Dict[str, Any]:
    """Compare two ``otel_sdk_spans.jsonl`` files for structural parity."""
    from mas.library.telemetry.verification.compare import compare_otel_span_files

    report = compare_otel_span_files(
        reference_path,
        candidate_path,
        strict=strict,
        reference_label=reference_label,
        candidate_label=candidate_label,
    )
    if output_path:
        Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if fail_on_error and not report.get("passed", False):
        logger.error(
            "compare_spans: parity FAILED (%s vs %s)", reference_label, candidate_label
        )
    return report


def run_compare_spans_multi(
    reference_path: str | Path,
    candidates: List[Tuple[str, str | Path]],
    *,
    strict: bool = True,
    output_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Compare one reference spans file against multiple labelled candidates."""
    from mas.library.telemetry.verification.compare import compare_otel_span_files_multi

    report = compare_otel_span_files_multi(reference_path, candidates, strict=strict)
    if output_path:
        Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


__all__ = ["run_compare_spans", "run_compare_spans_multi"]
