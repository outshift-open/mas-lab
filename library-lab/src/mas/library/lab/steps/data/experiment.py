#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Experiment step - runs N trials of an agent pattern on dataset.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext
from mas.lab.benchmark import MultiRunOrchestrator, ResultStorage


logger = logging.getLogger(__name__)


class ExperimentStep(PipelineStep):
    """Execute experiment trials on dataset."""
    
    type = "experiment"
    
    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        """Run experiment.
        
        Config:
            manifest: str - Path to agent manifest YAML
            n_runs: int - Number of runs per dataset item
            timeout: int - Timeout per run (seconds)
            pause_between_runs: float - Seconds between runs
        
        Requires dependency:
            Dataset step output (implicit via @dataset.output or explicit)
        
        Returns:
            StepOutput with summary in metadata
        """
        config = self.config
        
        # Get dataset from dependencies (auto-detect)
        dataset_step = None
        for dep_name in self.depends_on:
            dep_output = ctx.step_outputs.get(dep_name)
            if dep_output and "dataset" in dep_output.data:
                dataset = dep_output.data["dataset"]
                dataset_step = dep_name
                break
        
        if dataset is None:
            raise ValueError(f"Step '{self.name}': No dataset found in dependencies")
        
        logger.info(f"Step '{self.name}': Using dataset from '{dataset_step}'")
        
        # Setup storage
        output_dir = ctx.get_step_output_dir(self.name)
        storage = ResultStorage(output_dir)
        
        # Resolve manifest path
        manifest_path = Path(config["manifest"])
        if not manifest_path.is_absolute() and ctx.pipeline.config_path:
            manifest_path = ctx.pipeline.config_path.parent / manifest_path
        
        # Setup orchestrator
        orchestrator = MultiRunOrchestrator(
            storage=storage,
            n_runs=config.get("n_runs", 3),
            pause_between_runs=config.get("pause_between_runs", 1.0),
        )
        
        async def create_agent(pattern_name, pattern_config):
            raise NotImplementedError(
                f"Step '{self.name}': legacy experiment step is unsupported. "
                "Use execution.runner: native in experiment.yaml and mas-lab benchmark schedule."
            )
        
        # Run experiment
        patterns = {self.name: {"manifest": str(manifest_path)}}
        
        summary = await orchestrator.run_dataset(
            dataset=dataset,
            patterns=patterns,
            agent_factory=lambda pn, pc: create_agent(pn, pc),
        )
        
        # Collect output files
        result_files = list(storage.base_dir.rglob("*.json")) + list(
            storage.base_dir.rglob("*.jsonl")
        )
        
        return StepOutput(
            data={"summary": summary},
            files=result_files,
            metadata={
                "dataset": dataset.name,
                "pattern": self.name,
                "n_runs": config.get("n_runs", 3),
                "total_runs": summary.get("completed", 0) + summary.get("failed", 0),
                "completed": summary.get("completed", 0),
                "failed": summary.get("failed", 0),
            }
        )
    
    def outputs_exist(self, output_dir: Path) -> bool:
        """Check if experiment outputs exist."""
        step_output_dir = output_dir / "data" / self.name
        
        # Check if directory exists and has run data
        if not step_output_dir.exists():
            return False
        
        # Look for metadata.json files (indicate completed runs)
        metadata_files = list(step_output_dir.rglob("metadata.json"))
        return len(metadata_files) > 0
