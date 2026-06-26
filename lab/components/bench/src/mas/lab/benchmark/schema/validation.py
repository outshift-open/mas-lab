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
    NormalizedMetric,
    NormalizedRunInfo,
    NORMALIZED_METRICS_COLUMNS,
)

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Schema validation error."""
    pass


def validate_events_jsonl(path: Path) -> List[NormalizedEvent]:
    """
    Validate and parse events.jsonl file.
    
    Args:
        path: Path to events.jsonl
        
    Returns:
        List of NormalizedEvent objects
        
    Raises:
        ValidationError: If file is invalid
    """
    events = []
    
    if not path.exists():
        raise ValidationError(f"events.jsonl not found: {path}")
    
    try:
        with open(path, "r") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    event = NormalizedEvent.from_jsonl_line(line)
                    # Validate required fields
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
    
    logger.debug(f"Validated {len(events)} events from {path}")
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
