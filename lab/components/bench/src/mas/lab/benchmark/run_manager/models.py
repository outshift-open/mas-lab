#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark run summary models."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from mas.lab.benchmark.metadata import BenchmarkMetadata, BenchmarkStatus


@dataclass
class BenchmarkRunInfo:
    """Summary information about a benchmark run."""
    
    benchmark_id: str
    short_id: str
    timestamp: datetime
    experiment_name: str
    name: Optional[str]
    tags: List[str]
    status: BenchmarkStatus
    completion_rate: float
    total_scenarios: int
    completed_scenarios: int
    failed_scenarios: int
    n_scenarios: int
    n_tests: int
    n_runs_per_test: int
    run_dir: Path
    experiment_yaml_path: str = ""
    
    @classmethod
    def from_metadata(cls, metadata: BenchmarkMetadata, run_dir: Path) -> "BenchmarkRunInfo":
        """Create from metadata.
        
        Args:
            metadata: Benchmark metadata
            run_dir: Run directory path
            
        Returns:
            Run info summary
        """
        return cls(
            benchmark_id=metadata.benchmark_id,
            short_id=metadata.short_id,
            timestamp=datetime.fromisoformat(metadata.timestamp),
            experiment_name=metadata.experiment_name,
            name=metadata.name,
            tags=metadata.tags,
            status=metadata.status,
            completion_rate=metadata.completion_rate,
            total_scenarios=metadata.total_scenarios,
            completed_scenarios=metadata.completed_scenarios,
            failed_scenarios=metadata.failed_scenarios,
            n_scenarios=metadata.n_scenarios,
            n_tests=metadata.n_tests,
            n_runs_per_test=metadata.n_runs_per_test,
            run_dir=run_dir,
            experiment_yaml_path=metadata.experiment_yaml_path or "",
        )
