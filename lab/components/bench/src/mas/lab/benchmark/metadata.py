#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Benchmark run metadata management.

Each benchmark run has:
- Unique UUID
- Timestamp
- Metadata (experiment name, description, status, progress)
- Storage in $XDG_DATA_HOME/mas/benchmarks/<timestamp>_<uuid>/
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum
import yaml
import uuid
import os
import psutil


class BenchmarkStatus(Enum):
    """Status of a benchmark run."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    LOCKED = "locked"  # Another process is running this benchmark


class ScenarioState(Enum):
    """State of individual scenario execution."""
    TODO = "todo"  # Not started
    RUNNING = "running"  # Currently executing
    STALE = "stale"  # Was running but process died
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Failed with error


@dataclass
class BenchmarkMetadata:
    """Metadata for a benchmark run."""
    
    # Identification
    benchmark_id: str  # UUID
    timestamp: str  # ISO 8601 format
    
    # Experiment details
    experiment_name: str
    experiment_description: str
    experiment_yaml_path: str
    
    # Status
    status: BenchmarkStatus
    
    # Progress
    total_scenarios: int
    completed_scenarios: int = 0
    failed_scenarios: int = 0
    
    # Hierarchy counts (scenario > test > run)
    n_scenarios: int = 0     # Unique scenarios (scenario level)
    n_tests: int = 0        # Unique (variant × item) pairs (test level)
    n_runs_per_test: int = 1  # Runs per test
    
    # Timing
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    
    # Resources
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    
    # Intermediate statistics (computed periodically during execution)
    elapsed_seconds: Optional[float] = None  # Time elapsed since start
    throughput_scenarios_per_sec: Optional[float] = None  # Completion rate
    avg_tokens_per_scenario: Optional[float] = None  # Average tokens/scenario
    eta_seconds: Optional[float] = None  # Estimated time to completion
    last_update_at: Optional[str] = None  # Timestamp of last statistics update
    
    # Paths
    run_dir: str = ""
    results_file: str = ""
    plots_dir: str = ""
    
    # Process tracking
    process_pid: Optional[int] = None  # PID of process running this benchmark
    process_hostname: Optional[str] = None  # Hostname where process is running
    
    # User metadata
    name: Optional[str] = None  # User-defined name
    tags: List[str] = field(default_factory=list)  # User-defined tags
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create_new(
        cls,
        experiment_name: str,
        experiment_description: str,
        experiment_yaml_path: str,
        total_scenarios: int,
        run_dir: Path,
    ) -> "BenchmarkMetadata":
        """Create new benchmark metadata.
        
        Args:
            experiment_name: Name of experiment
            experiment_description: Description
            experiment_yaml_path: Path to experiment YAML
            total_scenarios: Total number of scenarios
            run_dir: Directory for this run
            
        Returns:
            New metadata instance
        """
        benchmark_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        return cls(
            benchmark_id=benchmark_id,
            timestamp=timestamp,
            experiment_name=experiment_name,
            experiment_description=experiment_description,
            experiment_yaml_path=str(experiment_yaml_path),
            status=BenchmarkStatus.RUNNING,
            total_scenarios=total_scenarios,
            started_at=timestamp,
            run_dir=str(run_dir),
            results_file=str(run_dir / "results.csv"),
            plots_dir=str(run_dir / "plots"),
        )
    
    @classmethod
    def from_yaml(cls, path: Path) -> "BenchmarkMetadata":
        """Load metadata from YAML file.

        Unknown keys in the YAML are silently ignored so that stale metadata
        files written by older versions of mas-lab don't crash the loader.
        """
        import dataclasses as _dc
        with open(path) as f:
            data = yaml.safe_load(f)

        # Convert status string to enum
        if isinstance(data.get("status"), str):
            data["status"] = BenchmarkStatus(data["status"])

        # Drop keys that no longer exist in the dataclass (backward compat).
        known = {f.name for f in _dc.fields(cls)}
        data = {k: v for k, v in data.items() if k in known}

        return cls(**data)
    
    def to_yaml(self, path: Path) -> None:
        """Save metadata to YAML file.
        
        Args:
            path: Path to save to
        """
        data = asdict(self)
        
        # Convert status enum to string
        data["status"] = self.status.value
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def update_progress(
        self,
        completed: int,
        failed: int,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        """Update progress counters and compute intermediate statistics.
        
        Args:
            completed: Number of completed scenarios
            failed: Number of failed scenarios
            tokens_input: Input tokens used (for this update)
            tokens_output: Output tokens used (for this update)
        """
        self.completed_scenarios = completed
        self.failed_scenarios = failed
        self.total_tokens_input += tokens_input
        self.total_tokens_output += tokens_output
        self.total_tokens = self.total_tokens_input + self.total_tokens_output
        
        # Estimate cost (Gemini pricing: $0.10/1M input, $0.30/1M output)
        self.estimated_cost_usd = (
            self.total_tokens_input * 0.10 / 1_000_000 +
            self.total_tokens_output * 0.30 / 1_000_000
        )
        
        # Compute intermediate statistics
        if self.started_at:
            started = datetime.fromisoformat(self.started_at)
            now = datetime.now()
            self.elapsed_seconds = (now - started).total_seconds()
            
            # Throughput (scenarios/sec)
            if self.elapsed_seconds > 0:
                self.throughput_scenarios_per_sec = self.completed_scenarios / self.elapsed_seconds
            else:
                self.throughput_scenarios_per_sec = 0.0
            
            # Average tokens per completed scenario
            if self.completed_scenarios > 0:
                self.avg_tokens_per_scenario = self.total_tokens / self.completed_scenarios
            else:
                self.avg_tokens_per_scenario = 0.0
            
            # ETA (estimated time to completion)
            remaining = self.total_scenarios - self.completed_scenarios
            if self.throughput_scenarios_per_sec and self.throughput_scenarios_per_sec > 0 and remaining > 0:
                self.eta_seconds = remaining / self.throughput_scenarios_per_sec
            else:
                self.eta_seconds = None
            
            # Update timestamp
            self.last_update_at = now.isoformat()
    
    def mark_completed(self) -> None:
        """Mark benchmark as completed."""
        self.status = BenchmarkStatus.COMPLETED
        self.completed_at = datetime.now().isoformat()
        
        if self.started_at:
            started = datetime.fromisoformat(self.started_at)
            completed = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (completed - started).total_seconds()
    
    def mark_failed(self, error: str = "") -> None:
        """Mark benchmark as failed.
        
        Args:
            error: Error message
        """
        self.status = BenchmarkStatus.FAILED
        self.completed_at = datetime.now().isoformat()
        
        if error:
            self.metadata["error"] = error
        
        if self.started_at:
            started = datetime.fromisoformat(self.started_at)
            completed = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (completed - started).total_seconds()
    
    def mark_interrupted(self) -> None:
        """Mark benchmark as interrupted."""
        self.status = BenchmarkStatus.INTERRUPTED
        self.completed_at = datetime.now().isoformat()
        
        if self.started_at:
            started = datetime.fromisoformat(self.started_at)
            completed = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (completed - started).total_seconds()
    
    @property
    def short_id(self) -> str:
        """Get short version of UUID (first 8 chars)."""
        return self.benchmark_id[:8]
    
    @property
    def completion_rate(self) -> float:
        """Get completion rate (0.0 to 1.0)."""
        if self.total_scenarios == 0:
            return 0.0
        return min(self.completed_scenarios / self.total_scenarios, 1.0)
    
    @property
    def success_rate(self) -> float:
        """Get success rate among completed scenarios."""
        completed = self.completed_scenarios
        if completed == 0:
            return 0.0
        successful = completed - self.failed_scenarios
        return successful / completed


@dataclass
class ScenarioResult:
    """Result of a single scenario execution."""
    
    scenario_id: str
    state: ScenarioState
    success: bool = False
    score: Optional[float] = None
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    process_pid: Optional[int] = None  # PID when scenario started
    result: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert state enum to string
        if isinstance(self.state, ScenarioState):
            data["state"] = self.state.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioResult":
        """Create from dictionary."""
        # Convert state string to enum
        if "state" in data and isinstance(data["state"], str):
            data["state"] = ScenarioState(data["state"])
        return cls(**data)


@dataclass
class BenchmarkState:
    """State of benchmark execution (for resume functionality)."""
    
    benchmark_id: str
    total_scenarios: int
    
    # Scenarios by status
    pending: List[str] = field(default_factory=list)
    """Scenario IDs not yet executed."""
    
    completed: Dict[str, ScenarioResult] = field(default_factory=dict)
    """Completed scenarios (success or failure)."""
    
    @property
    def completed_count(self) -> int:
        """Number of completed scenarios."""
        return len(self.completed)
    
    @property
    def pending_count(self) -> int:
        """Number of pending scenarios."""
        return len(self.pending)
    
    @property
    def failed_count(self) -> int:
        """Number of failed scenarios."""
        return sum(1 for r in self.completed.values() if not r.success)
    
    @property
    def success_count(self) -> int:
        """Number of successful scenarios."""
        return sum(1 for r in self.completed.values() if r.success)
    
    def mark_completed(self, scenario_id: str, result: ScenarioResult) -> None:
        """Mark scenario as completed.
        
        Args:
            scenario_id: Scenario identifier
            result: Execution result
        """
        if scenario_id in self.pending:
            self.pending.remove(scenario_id)
        self.completed[scenario_id] = result
    
    def is_completed(self, scenario_id: str) -> bool:
        """Check if scenario is already completed.
        
        Args:
            scenario_id: Scenario identifier
            
        Returns:
            True if completed
        """
        return scenario_id in self.completed
    
    @classmethod
    def create_new(
        cls,
        benchmark_id: str,
        scenario_ids: List[str],
    ) -> "BenchmarkState":
        """Create new state with all scenarios pending.
        
        Args:
            benchmark_id: Benchmark UUID
            scenario_ids: All scenario IDs to execute
            
        Returns:
            New state instance
        """
        return cls(
            benchmark_id=benchmark_id,
            total_scenarios=len(scenario_ids),
            pending=scenario_ids.copy(),
        )
    
    @classmethod
    def from_json(cls, path: Path) -> "BenchmarkState":
        """Load state from JSON file.
        
        Args:
            path: Path to state.json
            
        Returns:
            Loaded state
        """
        import json
        
        with open(path) as f:
            data = json.load(f)
        
        # Convert completed results dict
        completed = {
            scenario_id: ScenarioResult.from_dict(result_data)
            for scenario_id, result_data in data.get("completed", {}).items()
        }
        
        return cls(
            benchmark_id=data["benchmark_id"],
            total_scenarios=data["total_scenarios"],
            pending=data.get("pending", []),
            completed=completed,
        )
    
    def to_json(self, path: Path) -> None:
        """Save state to JSON file.
        
        Args:
            path: Path to save to
        """
        import json
        
        # Convert completed results to dicts
        completed_dict = {
            scenario_id: result.to_dict()
            for scenario_id, result in self.completed.items()
        }
        
        data = {
            "benchmark_id": self.benchmark_id,
            "total_scenarios": self.total_scenarios,
            "pending": self.pending,
            "completed": completed_dict,
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
