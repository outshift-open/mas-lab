#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Analysis step - consolidates experiment results into DataFrame.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext
from mas.lab.benchmark import ResultAnalyzer, ResultStorage


logger = logging.getLogger(__name__)


class AnalysisStep(PipelineStep):
    """Consolidate experiment results."""
    
    type = "analysis"
    
    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        """Analyze and consolidate results.
        
        Config:
            include_events: bool - Parse event logs for metrics (default: True)
            cache: bool - Save DataFrame as parquet (default: True)
            metrics: list - Metrics to extract (default: all available)
        
        Requires dependencies:
            One or more experiment steps
        
        Returns:
            StepOutput with DataFrame in data["dataframe"]
        """
        config = self.config
        
        # Find all experiment dependencies
        experiment_steps = []
        for dep_name in self.depends_on:
            dep_step = ctx.pipeline.get_step(dep_name)
            if dep_step and dep_step.type == "experiment":
                experiment_steps.append(dep_name)
        
        if not experiment_steps:
            raise ValueError(f"Step '{self.name}': No experiment steps found in dependencies")
        
        logger.info(f"Step '{self.name}': Analyzing {len(experiment_steps)} experiments")
        
        # Collect experiment output directories
        storage_dirs = [
            ctx.get_step_output_dir(exp_name)
            for exp_name in experiment_steps
        ]

        dataset_name = "unknown"
        for exp_name in experiment_steps:
            exp_output = ctx.step_outputs.get(exp_name)
            if exp_output and "dataset" in exp_output.metadata:
                dataset_name = exp_output.metadata["dataset"]
                break

        # Collect and merge results from all experiment storage roots
        import pandas as pd

        frames = []
        for storage_dir in storage_dirs:
            analyzer = ResultAnalyzer(ResultStorage(storage_dir))
            part = analyzer.consolidate_results(
                dataset_name=dataset_name,
                include_events=config.get("include_events", True),
                cache=False,
            )
            if not part.empty:
                part = part.copy()
                part["experiment_storage"] = str(storage_dir)
                frames.append(part)

        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        analyzer = ResultAnalyzer(ResultStorage(storage_dirs[0]))
        
        if df.empty:
            logger.warning(f"Step '{self.name}': No results found")
        
        # Compute statistics
        stats = analyzer.compute_statistics(df) if not df.empty else None
        
        # Save outputs
        output_dir = ctx.get_step_output_dir(self.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_files = []
        
        # Save DataFrame
        if config.get("cache", True) and not df.empty:
            df_path = output_dir / "consolidated.parquet"
            df.to_parquet(df_path)
            output_files.append(df_path)
            logger.info(f"Saved DataFrame: {df_path}")
        
        # Save statistics
        if stats is not None and not stats.empty:
            stats_path = output_dir / "statistics.csv"
            stats.to_csv(stats_path, index=False)
            output_files.append(stats_path)
            logger.info(f"Saved statistics: {stats_path}")
        
        return StepOutput(
            data={
                "dataframe": df,
                "statistics": stats,
            },
            files=output_files,
            metadata={
                "dataset": dataset_name,
                "experiments": experiment_steps,
                "rows": len(df),
                "columns": list(df.columns) if not df.empty else [],
            }
        )
    
    def outputs_exist(self, output_dir: Path) -> bool:
        """Check if consolidated results exist."""
        step_output_dir = output_dir / "data" / self.name
        
        # Check for parquet file
        parquet_file = step_output_dir / "consolidated.parquet"
        return parquet_file.exists()
