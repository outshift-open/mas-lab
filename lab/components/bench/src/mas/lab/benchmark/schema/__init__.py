#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Normalized schemas for benchmark outputs.

Defines:
- NormalizedEvent: Event schema for events.jsonl
- NormalizedMetric: Metric measurement schema
- NormalizedRunInfo: Run execution summary schema
- Validation utilities

All pipeline steps emit and consume these schemas.
"""

from .normalized import (
    NormalizedEvent,
    NormalizedMetric,
    NormalizedRunInfo,
    EventKind,
    NORMALIZED_METRICS_COLUMNS,
)
from .validation import (
    validate_metrics_csv,
    validate_events_jsonl,
    validate_run_info_json,
)

__all__ = [
    "NormalizedEvent",
    "NormalizedMetric",
    "NormalizedRunInfo",
    "EventKind",
    "NORMALIZED_METRICS_COLUMNS",
    "validate_metrics_csv",
    "validate_events_jsonl",
    "validate_run_info_json",
]
