#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Result storage with human-readable folder structure.

Folder layout:
results/
  {dataset_name}/
    {item_id}/
      {run_id}/
        metadata.json      # Run configuration & timing
        events.jsonl       # OTEL events
        logs/              # Agent logs
        artifacts/         # Intermediate files
    consolidated.parquet   # All runs DataFrame
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class RunMetadata:
    """Metadata for a single run."""
    dataset_name: str
    item_id: str
    run_id: str
    pattern: str
    timestamp: str
    config: Dict[str, Any]
    success: bool = False
    latency_ms: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResultStorage:
    """
    Manages result storage with incremental writes.
    
    Features:
    - Human-readable folder names
    - Incremental addition (no rerun needed)
    - Preserves all artifacts
    - DataFrame consolidation
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def get_run_dir(self, dataset_name: str, item_id: str, run_id: str) -> Path:
        """Get directory for specific run."""
        run_dir = self.base_dir / dataset_name / item_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    
    def generate_run_id(self, pattern: str, run_number: int) -> str:
        """Generate human-readable run ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{pattern}_run_{run_number:03d}_{timestamp}"
    
    def save_run(
        self,
        dataset_name: str,
        item_id: str,
        run_id: str,
        metadata: RunMetadata,
        events_file: Optional[Path] = None,
        artifacts: Optional[Dict[str, Path]] = None
    ) -> Path:
        """
        Save run results.
        
        Args:
            dataset_name: Dataset identifier
            item_id: Item identifier
            run_id: Run identifier
            metadata: Run metadata
            events_file: Path to events.jsonl to copy
            artifacts: Dict of artifact_name -> file_path to copy
            
        Returns:
            Path to run directory
        """
        run_dir = self.get_run_dir(dataset_name, item_id, run_id)
        
        # Save metadata
        metadata_file = run_dir / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        # Copy events if provided
        if events_file and events_file.exists():
            shutil.copy2(events_file, run_dir / "events.jsonl")
        
        # Copy artifacts if provided
        if artifacts:
            artifacts_dir = run_dir / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            for name, src_path in artifacts.items():
                if src_path.exists():
                    dest = artifacts_dir / name
                    if src_path.is_file():
                        shutil.copy2(src_path, dest)
                    elif src_path.is_dir():
                        shutil.copytree(src_path, dest, dirs_exist_ok=True)
        
        return run_dir
    
    def load_run_metadata(self, dataset_name: str, item_id: str, run_id: str) -> Optional[RunMetadata]:
        """Load metadata for specific run."""
        metadata_file = self.base_dir / dataset_name / item_id / run_id / "metadata.json"
        if not metadata_file.exists():
            return None
        
        with open(metadata_file) as f:
            data = json.load(f)
        return RunMetadata(**data)
    
    def list_runs(self, dataset_name: str, item_id: Optional[str] = None) -> List[tuple]:
        """
        List all runs.
        
        Returns:
            List of (dataset_name, item_id, run_id) tuples
        """
        runs = []
        dataset_dir = self.base_dir / dataset_name
        if not dataset_dir.exists():
            return runs
        
        if item_id:
            item_dirs = [dataset_dir / item_id]
        else:
            item_dirs = [d for d in dataset_dir.iterdir() if d.is_dir() and d.name != "consolidated.parquet"]
        
        for item_dir in item_dirs:
            if not item_dir.is_dir():
                continue
            for run_dir in item_dir.iterdir():
                if run_dir.is_dir() and (run_dir / "metadata.json").exists():
                    runs.append((dataset_name, item_dir.name, run_dir.name))
        
        return sorted(runs)
    
    def get_next_run_number(self, dataset_name: str, item_id: str, pattern: str) -> int:
        """Get next run number for pattern."""
        item_dir = self.base_dir / dataset_name / item_id
        if not item_dir.exists():
            return 1
        
        max_run = 0
        for run_dir in item_dir.iterdir():
            if run_dir.is_dir() and run_dir.name.startswith(pattern):
                # Extract run number from "{pattern}_run_{number}_*"
                parts = run_dir.name.split("_")
                if len(parts) >= 3 and parts[1] == "run":
                    try:
                        run_num = int(parts[2])
                        max_run = max(max_run, run_num)
                    except ValueError:
                        continue
        
        return max_run + 1
    
    def clean_dataset(self, dataset_name: str) -> None:
        """Remove all runs for a dataset."""
        dataset_dir = self.base_dir / dataset_name
        if dataset_dir.exists():
            shutil.rmtree(dataset_dir)
    
    def get_consolidated_path(self, dataset_name: str) -> Path:
        """Get path to consolidated DataFrame."""
        return self.base_dir / dataset_name / "consolidated.parquet"
