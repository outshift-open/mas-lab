#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Reusable benchmark infrastructure for MAS evaluations.

Provides composable primitives for:
- Dataset management
- Multi-run orchestration  
- Incremental results storage
- DataFrame consolidation
- Declarative evaluation configuration
"""

from mas.lab.benchmark.dataset import Dataset, DatasetItem
from mas.lab.benchmark.runner import MultiRunOrchestrator
from mas.lab.benchmark.storage import ResultStorage, RunMetadata
from mas.lab.benchmark.metadata import (
    BenchmarkMetadata,
    BenchmarkState,
    BenchmarkStatus,
    ScenarioResult,
    ScenarioState,
)
from mas.lab.benchmark.state import EnhancedBenchmarkState
from mas.lab.benchmark.lock import BenchmarkLock, LockInfo

__all__ = [
    "Dataset",
    "DatasetItem",
    "MultiRunOrchestrator",
    "ResultStorage",
    "RunMetadata",
    "ResultAnalyzer",
    "BenchmarkMetadata",
    "BenchmarkState",
    "BenchmarkStatus",
    "ScenarioResult",
    "ScenarioState",
    "EnhancedBenchmarkState",
    "BenchmarkLock",
    "LockInfo",
    "ExperimentResults",
    "ScenarioView",
    "ItemView",
    "RunView",
]


def __getattr__(name: str):
    # Defer pandas imports so coverage tracing of pipeline subpackages does not
    # reload numpy during test collection (pytest-cov / coverage.py on Py 3.11+).
    if name == "ResultAnalyzer":
        from mas.lab.benchmark.analysis import ResultAnalyzer

        return ResultAnalyzer
    if name in ("ExperimentResults", "ScenarioView", "ItemView", "RunView"):
        from mas.lab.benchmark.results import (
            ExperimentResults,
            ItemView,
            RunView,
            ScenarioView,
        )

        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
