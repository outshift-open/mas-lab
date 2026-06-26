#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Enhanced benchmark state management with granular scenario tracking.

This module provides robust state management for benchmark execution with:
- Granular scenario states (todo, running, stale, completed, failed)
- Stale detection (processes that died)
- Resume priority (stale first, then todo)
"""

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import json

from mas.lab.benchmark.metadata import ScenarioResult, ScenarioState


logger = logging.getLogger(__name__)


@dataclass
class EnhancedBenchmarkState:
    """Enhanced state tracking with granular scenario states.
    
    Each scenario has one of:
    - TODO: Not started yet
    - RUNNING: Currently executing
    - STALE: Was running but process died
    - COMPLETED: Successfully finished
    - FAILED: Failed with error
    """
    
    benchmark_id: str
    total_scenarios: int
    scenarios: Dict[str, ScenarioResult] = field(default_factory=dict)
    
    def get_by_state(self, state: ScenarioState) -> List[str]:
        """Get scenario IDs by state."""
        return [
            sid for sid, result in self.scenarios.items()
            if result.state == state
        ]
    
    @property
    def todo_scenarios(self) -> List[str]:
        """Not yet started."""
        return self.get_by_state(ScenarioState.TODO)
    
    @property
    def running_scenarios(self) -> List[str]:
        """Currently executing."""
        return self.get_by_state(ScenarioState.RUNNING)
    
    @property
    def stale_scenarios(self) -> List[str]:
        """Was running but process died."""
        return self.get_by_state(ScenarioState.STALE)
    
    @property
    def completed_scenarios(self) -> List[str]:
        """Successfully completed."""
        return self.get_by_state(ScenarioState.COMPLETED)
    
    @property
    def failed_scenarios(self) -> List[str]:
        """Failed with error."""
        return self.get_by_state(ScenarioState.FAILED)
    
    @property
    def pending_scenarios(self) -> List[str]:
        """Ready to execute (priority: stale > todo)."""
        return self.stale_scenarios + self.todo_scenarios
    
    @property
    def completed_count(self) -> int:
        """Completed + failed."""
        return len(self.completed_scenarios) + len(self.failed_scenarios)
    
    @property
    def pending_count(self) -> int:
        """Stale + todo."""
        return len(self.pending_scenarios)
    
    @property
    def success_count(self) -> int:
        """Successfully completed."""
        return len(self.completed_scenarios)
    
    @property
    def failed_count(self) -> int:
        """Failed."""
        return len(self.failed_scenarios)
    
    # Legacy compatibility
    @property
    def pending(self) -> List[str]:
        """Legacy: pending scenarios."""
        return self.pending_scenarios
    
    @ property
    def completed(self) -> Dict[str, ScenarioResult]:
        """Legacy: completed scenarios."""
        return {
            sid: result for sid, result in self.scenarios.items()
            if result.state in (ScenarioState.COMPLETED, ScenarioState.FAILED)
        }
    
    def initialize_scenarios(self, scenario_ids: List[str]) -> None:
        """Initialize all scenarios as TODO.
        
        Args:
            scenario_ids: List of scenario IDs
        """
        for scenario_id in scenario_ids:
            if scenario_id not in self.scenarios:
                self.scenarios[scenario_id] = ScenarioResult(
                    scenario_id=scenario_id,
                    state=ScenarioState.TODO,
                )
    
    def mark_started(self, scenario_id: str, pid: int) -> None:
        """Mark scenario as started (RUNNING).
        
        Args:
            scenario_id: Scenario ID
            pid: Process ID
        """
        if scenario_id not in self.scenarios:
            self.scenarios[scenario_id] = ScenarioResult(
                scenario_id=scenario_id,
                state=ScenarioState.TODO,
            )
        
        result = self.scenarios[scenario_id]
        result.state = ScenarioState.RUNNING
        result.started_at = datetime.now().isoformat()
        result.process_pid = pid
    
    def mark_completed(self, scenario_id: str, result: ScenarioResult) -> None:
        """Mark scenario as completed (COMPLETED or FAILED).
        
        Args:
            scenario_id: Scenario ID
            result: Result with success/failure info
        """
        result.completed_at = datetime.now().isoformat()
        result.state = ScenarioState.COMPLETED if result.success else ScenarioState.FAILED
        self.scenarios[scenario_id] = result
    
    def detect_stale(self) -> int:
        """Detect and mark stale scenarios (RUNNING but process died).
        
        Returns:
            Number of stale scenarios detected
        """
        from mas.lab.benchmark.lock import detect_stale_scenarios
        
        stale_ids = detect_stale_scenarios(self.scenarios)
        
        for scenario_id in stale_ids:
            logger.warning(f"Detected stale scenario: {scenario_id}")
            self.scenarios[scenario_id].state = ScenarioState.STALE
        
        return len(stale_ids)
    
    def is_completed(self, scenario_id: str) -> bool:
        """Check if scenario is done (COMPLETED or FAILED).
        
        Args:
            scenario_id: Scenario ID
            
        Returns:
            True if completed or failed
        """
        if scenario_id not in self.scenarios:
            return False
        
        state = self.scenarios[scenario_id].state
        return state in (ScenarioState.COMPLETED, ScenarioState.FAILED)
    
    @classmethod
    def create_new(cls, benchmark_id: str, scenario_ids: List[str]) -> "EnhancedBenchmarkState":
        """Create new state with all scenarios as TODO.
        
        Args:
            benchmark_id: Benchmark UUID
            scenario_ids: All scenario IDs
            
        Returns:
            New state instance
        """
        state = cls(
            benchmark_id=benchmark_id,
            total_scenarios=len(scenario_ids),
        )
        state.initialize_scenarios(scenario_ids)
        return state
    
    @classmethod
    def from_json(cls, path: Path) -> "EnhancedBenchmarkState":
        """Load state from JSON.
        
        Args:
            path: Path to state.json
            
        Returns:
            Loaded state
        """
        with open(path) as f:
            data = json.load(f)
        
        # Convert scenarios dict
        scenarios = {
            scenario_id: ScenarioResult.from_dict(result_data)
            for scenario_id, result_data in data.get("scenarios", {}).items()
        }
        
        state = cls(
            benchmark_id=data["benchmark_id"],
            total_scenarios=data["total_scenarios"],
            scenarios=scenarios,
        )
        
        # Auto-detect stale on load
        stale_count = state.detect_stale()
        if stale_count > 0:
            logger.info(f"Detected {stale_count} stale scenarios on load")
        
        return state
    
    def to_json(self, path: Path) -> None:
        """Save state to JSON.
        
        Args:
            path: Path to save to
        """
        data = {
            "benchmark_id": self.benchmark_id,
            "total_scenarios": self.total_scenarios,
            "scenarios": {
                scenario_id: result.to_dict()
                for scenario_id, result in self.scenarios.items()
            },
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_summary(self) -> Dict[str, int]:
        """Get summary of scenario states.
        
        Returns:
            Dict with counts per state
        """
        return {
            "todo": len(self.todo_scenarios),
            "running": len(self.running_scenarios),
            "stale": len(self.stale_scenarios),
            "completed": len(self.completed_scenarios),
            "failed": len(self.failed_scenarios),
            "total": self.total_scenarios,
        }
