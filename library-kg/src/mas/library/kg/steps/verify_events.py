#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Standalone step: events.jsonl schema + spec validation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Literal

logger = logging.getLogger(__name__)

StrictnessMode = Literal["required", "recommended", "complete"]


def run_verify_events(
    events_path: str | Path,
    *,
    strictness: StrictnessMode = "required",
    fail_on_error: bool = False,
) -> Dict[str, Any]:
    """Validate an events.jsonl file against the JSON schema and events.spec.yaml.

    Args:
        events_path: Path to events.jsonl.
        strictness: Validation level — ``"required"`` (errors only),
            ``"recommended"`` (errors + warnings), ``"complete"`` (all rules).
        fail_on_error: Raise ``ValueError`` if any errors are found.

    Returns:
        Dict with keys:
            ``error_count``     — number of error-level violations
            ``warning_count``   — number of warning-level violations
            ``event_count``     — number of events validated
            ``violations``      — list of violation dicts
    """
    from mas.library.kg.observability.native.validate import EventValidator

    events_path = Path(events_path).expanduser().resolve()
    logger.info("verify_events: validating %s", events_path)

    from mas.library.kg.observability.native.validate import load_events

    validator = EventValidator()
    events = load_events(events_path)
    report = validator.validate(events, strictness=strictness)
    violations = report.violations

    error_count = sum(1 for v in violations if v.severity == "error")
    warning_count = sum(1 for v in violations if v.severity == "warning")

    # Count events
    event_count = 0
    with events_path.open() as fh:
        for line in fh:
            if line.strip():
                event_count += 1

    if fail_on_error and error_count:
        raise ValueError(
            f"events.jsonl validation failed: {error_count} error(s), {warning_count} warning(s)"
        )

    return {
        "error_count": error_count,
        "warning_count": warning_count,
        "event_count": event_count,
        "violations": [v.to_dict() for v in violations],
    }
