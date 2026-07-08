#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Dataset step - loads and filters evaluation datasets.
"""

from pathlib import Path
from typing import Any, Dict

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext
from mas.lab.benchmark import Dataset


class DatasetStep(PipelineStep):
    """Load and filter dataset."""
    
    type = "dataset"
    
    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        """Load dataset from JSON file.
        
        Config:
            path: str - Path to dataset JSON file
            filter: dict - Optional filters (category, etc.)
        
        Returns:
            StepOutput with dataset in data["dataset"]
        """
        config = self.config
        
        # Resolve path (relative to pipeline config)
        dataset_path = Path(config["path"])
        if not dataset_path.is_absolute() and ctx.pipeline.config_path:
            dataset_path = ctx.pipeline.config_path.parent / dataset_path
        
        # Load dataset
        dataset = Dataset.from_yaml(dataset_path)
        
        # Apply filters
        if "filter" in config and config["filter"]:
            dataset = dataset.filter(**config["filter"])
        
        # Save to output directory
        output_dir = ctx.get_step_output_dir(self.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"{dataset.name}.yaml"
        dataset.to_yaml(output_path)
        
        return StepOutput(
            data={"dataset": dataset},
            files=[output_path],
            metadata={
                "name": dataset.name,
                "version": dataset.version,
                "count": len(dataset),
                "source": str(dataset_path),
            }
        )
    
    def outputs_exist(self, output_dir: Path) -> bool:
        """Check if dataset output file exists."""
        step_output_dir = output_dir / "data" / self.name
        
        # We don't know dataset name without executing, so check if directory exists
        return step_output_dir.exists() and any(step_output_dir.glob("*.json"))
