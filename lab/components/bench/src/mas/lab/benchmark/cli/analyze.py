#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark analyze command."""

import logging
from pathlib import Path

from mas.lab.benchmark.run_manager import BenchmarkRunManager
from mas.lab.benchmark.reporting import print_benchmark_summary

from mas.lab.benchmark.cli.common import _resolve_run_manager_dir

logger = logging.getLogger(__name__)

def analyze_command(args) -> int:
    """Regenerate statistics and plots from existing results."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )
    
    # Get run
    result = run_manager.get_run(args.benchmark_id)
    if not result:
        logger.error(f"Benchmark run not found: {args.benchmark_id}")
        return 1
    
    metadata, run_dir = result
    
    # Load results CSV
    results_path = run_dir / "results.csv"
    if not results_path.exists():
        logger.error(f"Results file not found: {results_path}")
        return 1
    
    logger.info(f"Analyzing benchmark: {metadata.short_id}")
    logger.info(f"  Run directory: {run_dir}")
    
    # Load experiment.yaml (needed for plot config)
    experiment_yaml_path = None
    
    # Try user-provided path first
    if hasattr(args, "experiment_yaml") and args.experiment_yaml:
        experiment_yaml_path = Path(args.experiment_yaml)
        if not experiment_yaml_path.exists():
            logger.error(f"Provided experiment YAML not found: {args.experiment_yaml}")
            return 1
    else:
        # Try auto-detection in common locations
        search_paths = [
            # Original absolute or CWD-relative path
            Path(metadata.experiment_yaml_path),
            # Relative to run directory
            run_dir / metadata.experiment_yaml_path,
            # Relative to CWD
            Path.cwd() / metadata.experiment_yaml_path,
        ]
        
        for path in search_paths:
            if path.exists():
                experiment_yaml_path = path
                logger.info(f"  Found experiment.yaml: {path}")
                break
    
    if experiment_yaml_path and experiment_yaml_path.exists():
        from mas.lab.lab.config import MASExperimentConfig

        experiment = MASExperimentConfig.from_yaml(experiment_yaml_path)
    else:
        logger.error(f"Experiment YAML not found. Tried: {metadata.experiment_yaml_path}")
        logger.warning("Cannot generate plots without experiment configuration")
        logger.info("Hint: Use --experiment-yaml path/to/experiment.yaml to specify the file")
        experiment = None
    
    # Load CSV
    import pandas as pd
    df = pd.read_csv(results_path)
    logger.info(f"Loaded {len(df)} results")
    
    # Print statistics
    print()
    print_benchmark_summary(
        df,
        n_scenarios=metadata.n_scenarios or df["scenario"].nunique(),
        n_tests=metadata.n_tests or df.groupby(["scenario", "item_id"]).ngroups,
        n_runs_per_test=metadata.n_runs_per_test or df["run_id"].nunique(),
    )
    
    logger.info(
        "Figures and tables are produced by pipeline steps in experiment.yaml "
        "(application.post / scenario.post). Re-run the benchmark or "
        "'mas-lab benchmark step restart' to refresh plot artefacts."
    )

    return 0


