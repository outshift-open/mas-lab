#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Result analysis and DataFrame consolidation.

Loads all run metadata and creates consolidated DataFrames for analysis.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from mas.lab.benchmark.storage import ResultStorage


class ResultAnalyzer:
    """
    Analyze benchmark results.
    
    Features:
    - Consolidate all runs into DataFrame
    - Compute statistics per pattern
    - Extract metrics from event logs
    - Cache results as Parquet
    """
    
    def __init__(self, storage: ResultStorage):
        self.storage = storage
    
    def consolidate_results(
        self,
        dataset_name: str,
        include_events: bool = False,
        cache: bool = True
    ) -> pd.DataFrame:
        """
        Consolidate all runs into DataFrame.
        
        Args:
            dataset_name: Dataset name
            include_events: Parse event logs for detailed metrics
            cache: Save as Parquet for incremental updates
            
        Returns:
            DataFrame with columns:
            - dataset_name, item_id, run_id, pattern
            - timestamp, success, latency_ms, error
            - (if include_events) total_tokens, tool_calls, etc.
        """
        runs = self.storage.list_runs(dataset_name)
        
        if not runs:
            return pd.DataFrame()
        
        rows = []
        for ds_name, item_id, run_id in runs:
            metadata = self.storage.load_run_metadata(ds_name, item_id, run_id)
            if not metadata:
                continue
            
            row = {
                "dataset_name": metadata.dataset_name,
                "item_id": metadata.item_id,
                "run_id": metadata.run_id,
                "pattern": metadata.pattern,
                "timestamp": metadata.timestamp,
                "success": metadata.success,
                "latency_ms": metadata.latency_ms,
                "error": metadata.error,
            }
            
            # Add config fields
            for key, value in metadata.config.items():
                row[f"config_{key}"] = value
            
            # Parse events if requested
            if include_events:
                run_dir = self.storage.get_run_dir(ds_name, item_id, run_id)
                events_file = run_dir / "events.jsonl"
                if events_file.exists():
                    event_metrics = self._extract_event_metrics(events_file)
                    row.update(event_metrics)
            
            rows.append(row)
        
        df = pd.DataFrame(rows)
        
        # Cache as Parquet
        if cache and not df.empty:
            cache_path = self.storage.get_consolidated_path(dataset_name)
            df.to_parquet(cache_path, index=False)
        
        return df
    
    def load_cached(self, dataset_name: str) -> Optional[pd.DataFrame]:
        """Load cached consolidated DataFrame."""
        cache_path = self.storage.get_consolidated_path(dataset_name)
        if not cache_path.exists():
            return None
        return pd.read_parquet(cache_path)
    
    def compute_statistics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute aggregate statistics per pattern.
        
        Returns:
            DataFrame with pattern-level statistics:
            - mean_latency_ms, std_latency_ms
            - success_rate
            - mean_tokens, mean_tool_calls (if available)
        """
        if df.empty:
            return pd.DataFrame()
        
        # Basic statistics
        stats = df.groupby("pattern").agg({
            "latency_ms": ["mean", "std", "min", "max"],
            "success": "mean",
        })
        
        # Flatten column names
        stats.columns = ["_".join(col).strip("_") for col in stats.columns]
        stats = stats.rename(columns={"success_mean": "success_rate"})
        
        # Token and tool metrics if available
        if "total_tokens" in df.columns:
            token_stats = df.groupby("pattern")["total_tokens"].agg(["mean", "std"])
            token_stats.columns = ["mean_tokens", "std_tokens"]
            stats = stats.join(token_stats)
        
        if "tool_calls" in df.columns:
            tool_stats = df.groupby("pattern")["tool_calls"].agg(["mean", "std"])
            tool_stats.columns = ["mean_tool_calls", "std_tool_calls"]
            stats = stats.join(tool_stats)
        
        return stats.reset_index()
    
    def _extract_event_metrics(self, events_file: Path) -> Dict[str, Any]:
        """Extract metrics from event log."""
        metrics = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tool_calls": 0,
            "llm_calls": 0,
        }
        
        with open(events_file) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    
                    # Count LLM calls
                    if event.get("kind") == "llm_response":
                        metrics["llm_calls"] += 1
                        usage = event.get("usage", {})
                        metrics["total_tokens"] += usage.get("total_tokens", 0)
                        metrics["prompt_tokens"] += usage.get("prompt_tokens", 0)
                        metrics["completion_tokens"] += usage.get("completion_tokens", 0)
                    
                    # Count tool calls
                    elif event.get("kind") == "tool_start":
                        metrics["tool_calls"] += 1
                    
                except json.JSONDecodeError:
                    continue
        
        return metrics
    
    def get_item_runs(self, df: pd.DataFrame, item_id: str) -> pd.DataFrame:
        """Get all runs for specific item."""
        return df[df["item_id"] == item_id].copy()
    
    def get_pattern_runs(self, df: pd.DataFrame, pattern: str) -> pd.DataFrame:
        """Get all runs for specific pattern."""
        return df[df["pattern"] == pattern].copy()
    
    def compare_patterns(
        self,
        df: pd.DataFrame,
        patterns: List[str],
        metric: str = "latency_ms"
    ) -> pd.DataFrame:
        """
        Compare patterns on specific metric.
        
        Returns:
            DataFrame with item_id, pattern, metric columns
        """
        filtered = df[df["pattern"].isin(patterns)]
        return filtered.pivot_table(
            index="item_id",
            columns="pattern",
            values=metric,
            aggfunc="mean"
        ).reset_index()
