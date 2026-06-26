#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Normalized schema definitions for benchmark outputs.

Standardizes:
- Event schema (events.jsonl)
- Metrics schema (metrics.csv)
- Run info schema (run_info.json)

All steps emit this schema; consumers read the same structure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
from enum import Enum


class EventKind(Enum):
    """Enumeration of event kinds."""
    
    # Execution events
    RUN_START = "run_start"
    RUN_END = "run_end"
    AGENT_MESSAGE = "agent_message"
    TOOL_INVOKED = "tool_invoked"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    
    # Evaluation events
    EVAL_START = "eval_start"
    EVAL_END = "eval_end"
    METRIC_COMPUTED = "metric_computed"
    
    # System events
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"


@dataclass
class NormalizedEvent:
    """Normalized event format."""
    
    kind: str
    """Event kind (from EventKind enum)."""
    
    timestamp: str
    """ISO 8601 timestamp with microseconds."""
    
    properties: Dict[str, Any] = field(default_factory=dict)
    """Event-specific properties."""
    
    def to_jsonl_line(self) -> str:
        """Serialize to JSONL line."""
        return json.dumps({
            "kind": self.kind,
            "timestamp": self.timestamp,
            "properties": self.properties,
        })
    
    @staticmethod
    def from_jsonl_line(line: str) -> "NormalizedEvent":
        """Parse from JSONL line."""
        data = json.loads(line)
        return NormalizedEvent(
            kind=data["kind"],
            timestamp=data["timestamp"],
            properties=data["properties"],
        )


@dataclass
class NormalizedMetric:
    """A single metric measurement.
    
    NOTE: ``metric`` (not ``metric_name``) matches the live column convention
    used by collect_metrics, compute_ci, ci_plot and all downstream steps.
    """
    
    scenario: str
    """Scenario/condition name."""
    
    item_id: str
    """Dataset item ID."""
    
    metric: str
    """Metric name (e.g., 'answer_relevancy', 'goal_success_rate')."""
    
    value: float
    """Metric value."""
    
    cache_key: Optional[str] = None
    """Unified cache key linking this metric row to its execution trace."""
    
    run_hash: Optional[str] = None
    """Content-addressed trace hash (run_info.json run_hash)."""
    
    confidence_low: Optional[float] = None
    """Lower bound of 95% confidence interval."""
    
    confidence_high: Optional[float] = None
    """Upper bound of 95% confidence interval."""
    
    unit: str = ""
    """Optional unit (e.g., 'seconds', '%')."""
    
    tags: Dict[str, str] = field(default_factory=dict)
    """Optional tags for filtering (e.g., {'category': 'reasoning'})."""
    
    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to CSV row dict."""
        return {
            "scenario": self.scenario,
            "item_id": self.item_id,
            "metric": self.metric,
            "value": self.value,
            "cache_key": self.cache_key,
            "run_hash": self.run_hash,
            "confidence_low": self.confidence_low,
            "confidence_high": self.confidence_high,
            "unit": self.unit,
            "tags": json.dumps(self.tags) if self.tags else "",
        }


@dataclass
class NormalizedRunInfo:
    """Execution summary for a single run — matches run_info.json schema v1."""
    
    run_hash: str
    """Content-addressed trace hash."""
    
    experiment: str
    """Experiment name."""
    
    scenario: str
    """Scenario name."""
    
    item_id: str
    """Dataset item ID."""
    
    run_idx: int
    """Run index (0-based)."""
    
    model: str
    """Model used."""
    
    status: str
    """'ok', 'failed', 'timeout', etc."""
    
    elapsed_ms: float
    """Execution latency in milliseconds."""
    
    recorded_at: str
    """ISO 8601 timestamp when run was recorded."""
    
    cache_key: Optional[str] = None
    """Unified cache key linking this run to the cache store."""
    
    error: str = ""
    """Error message if status != 'ok'."""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1",
            "run_hash": self.run_hash,
            "cache_key": self.cache_key or "",
            "experiment": self.experiment,
            "scenario": self.scenario,
            "item_id": self.item_id,
            "run_idx": self.run_idx,
            "model": self.model,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "recorded_at": self.recorded_at,
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "NormalizedRunInfo":
        return NormalizedRunInfo(
            run_hash=data["run_hash"],
            experiment=data.get("experiment", ""),
            scenario=data["scenario"],
            item_id=data["item_id"],
            run_idx=int(data.get("run_idx", 0)),
            model=data.get("model", ""),
            status=data["status"],
            elapsed_ms=float(data.get("elapsed_ms", 0)),
            recorded_at=data["recorded_at"],
            cache_key=data.get("cache_key") or None,
            error=data.get("error", ""),
        )


# CSV headers for metrics (matches live collect_metrics column convention)
NORMALIZED_METRICS_COLUMNS = [
    "scenario",
    "item_id",
    "metric",
    "value",
    "cache_key",
    "run_hash",
    "confidence_low",
    "confidence_high",
    "unit",
    "tags",
]
