#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Schema validation utilities.

Validates that outputs conform to normalized schema before storage.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .normalized import (
    NormalizedEvent,
    NormalizedRunInfo,
)

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Schema validation error."""
    pass


# ---------------------------------------------------------------------------
# Trace integrity
# ---------------------------------------------------------------------------

def check_trace_integrity(events: list[dict], *, source: str = "") -> list[str]:
    """Return a list of structural integrity warnings for a raw event list.

    Checks all three trace sources (native events.jsonl, OTel-replay, KG)
    using the same predicate so mismatches across sources are comparable.

    Current checks
    --------------
    self_referential_start
        A ``*_start`` event where ``call_id == parent_call_id``.  This is
        impossible in a valid call tree and indicates the runtime's inner-layer
        ObservabilityOperator wrapper emitted a duplicate outer frame.  Such
        events produce orphaned records and inflated bar lengths in plots.
    """
    issues: list[str] = []
    tag = f"[{source}] " if source else ""

    for i, ev in enumerate(events):
        kind = ev.get("kind", "")
        if not kind.endswith("_start"):
            continue
        cid = ev.get("call_id")
        pid = ev.get("parent_call_id")
        if cid and pid and cid == pid:
            issues.append(
                f"{tag}event #{i} kind={kind!r} call_id={cid!r}: "
                "self-referential (call_id == parent_call_id) — "
                "runtime emitted inner-layer duplicate outer frame"
            )

    return issues


def validate_events_jsonl(path: Path) -> List[NormalizedEvent]:
    """Validate and parse events.jsonl file.

    Args:
        path: Path to events.jsonl

    Returns:
        List of NormalizedEvent objects

    Raises:
        ValidationError: If file is invalid
    """
    if not path.exists():
        raise ValidationError(f"events.jsonl not found: {path}")

    raw: list[dict] = []
    events: List[NormalizedEvent] = []

    try:
        with open(path, "r") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    raw.append(data)
                    event = NormalizedEvent.from_jsonl_line(line)
                    if not event.kind:
                        raise ValidationError(f"Line {i}: missing 'kind'")
                    if not event.timestamp:
                        raise ValidationError(f"Line {i}: missing 'timestamp'")
                    events.append(event)
                except json.JSONDecodeError as e:
                    raise ValidationError(f"Line {i}: invalid JSON: {e}")
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Failed to read events.jsonl: {e}")

    logger.debug("Validated %d events from %s", len(events), path)

    # Structural integrity — warn on self-referential start events so the bug
    # is visible in logs for every trace source (native, OTel-replay, KG).
    for issue in check_trace_integrity(raw, source=path.name):
        logger.warning("trace integrity: %s", issue)

    return events


def validate_metrics_csv(path: Path) -> pd.DataFrame:
    """
    Validate and parse metrics.csv file.
    
    Args:
        path: Path to metrics.csv
        
    Returns:
        Pandas DataFrame with normalized metrics
        
    Raises:
        ValidationError: If file is invalid
    """
    if not path.exists():
        raise ValidationError(f"metrics.csv not found: {path}")
    
    try:
        df = pd.read_csv(path)
        
        # Check required columns (uses 'metric' to match collect_metrics convention)
        required = ["scenario", "item_id", "metric", "value"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValidationError(f"Missing required columns: {missing}")
        
        # Validate types
        if not pd.api.types.is_numeric_dtype(df["value"]):
            raise ValidationError("'value' column must be numeric")
        
        if "confidence_low" in df.columns:
            if not pd.api.types.is_numeric_dtype(df["confidence_low"]):
                raise ValidationError("'confidence_low' column must be numeric")
        
        if "confidence_high" in df.columns:
            if not pd.api.types.is_numeric_dtype(df["confidence_high"]):
                raise ValidationError("'confidence_high' column must be numeric")
        
        logger.debug(f"Validated {len(df)} metric rows from {path}")
        return df
    
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Failed to read metrics.csv: {e}")


def validate_run_info_json(path: Path) -> NormalizedRunInfo:
    """
    Validate and parse run_info.json file.
    
    Args:
        path: Path to run_info.json
        
    Returns:
        NormalizedRunInfo object
        
    Raises:
        ValidationError: If file is invalid
    """
    if not path.exists():
        raise ValidationError(f"run_info.json not found: {path}")
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
        
        # Validate required fields — matches run_info.json schema v1
        required = ["run_hash", "item_id", "scenario", "status", "elapsed_ms", "recorded_at"]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValidationError(f"Missing required fields: {missing}")
        
        # Validate types
        if not isinstance(data["elapsed_ms"], (int, float)):
            raise ValidationError("'elapsed_ms' must be numeric")
        
        info = NormalizedRunInfo.from_dict(data)
        logger.debug(f"Validated run_info for {info.item_id}")
        return info
    
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Failed to read run_info.json: {e}")
