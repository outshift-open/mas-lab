#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Resume MAS batch benchmarks via trace idempotency (skip completed runs)."""

import logging
from pathlib import Path
from typing import Optional

from mas.lab.benchmark.run_manager import BenchmarkRunManager

logger = logging.getLogger(__name__)


async def resume_mas_benchmark(
    *,
    experiment_yaml: Path,
    benchmark_id: Optional[str] = None,
    progress: bool = True,
    run_manager: Optional[BenchmarkRunManager] = None,
    force_lock: bool = False,
) -> bool:
    """Continue a MAS benchmark in *run_dir* — re-runs only missing/empty traces."""
    rm = run_manager or BenchmarkRunManager()

    if benchmark_id:
        result = rm.get_run(benchmark_id)
        if not result:
            logger.error("Benchmark run not found: %s", benchmark_id)
            return False
        metadata, run_dir = result
    else:
        found = rm.find_resumable_run()
        if not found:
            logger.error("No resumable benchmark runs found")
            logger.info("Tip: use 'mas-lab benchmark list' to see all runs")
            return False
        metadata, _state, run_dir = found

    logger.info("Resuming benchmark: %s", metadata.short_id)
    logger.info("  Experiment: %s", metadata.experiment_name)
    logger.info("  Progress: %s/%s scenarios", metadata.completed_scenarios, metadata.total_scenarios)

    rm.record_last_run(metadata, run_dir)

    exp_yaml = Path(metadata.experiment_yaml_path)
    if not exp_yaml.exists():
        logger.warning("Original experiment YAML not found: %s", exp_yaml)
        exp_yaml = experiment_yaml

    if force_lock:
        from mas.lab.benchmark.lock import BenchmarkLock

        lock = BenchmarkLock(run_dir)
        try:
            lock.acquire(force=True)
        except RuntimeError as exc:
            logger.error("%s", exc)
            return False

    from mas.lab.benchmark.schedule.run_batch import run_mas_benchmark

    return await run_mas_benchmark(
        experiment_yaml=exp_yaml,
        progress=progress,
        output_dir=run_dir,
        force=False,
    )
