#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark engine — MAS experiments only; no CLI concerns."""

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkRunOptions:
    progress: bool = True
    resume: bool = False
    force: bool = False
    benchmark_id: str | None = None
    dry_run: bool = False
    max_runs: int | None = None
    limit_scenarios: int | None = None
    sample_scenarios: int | None = None
    single_run: bool = False
    output_dir: Path | None = None
    force_lock: bool = False
    flavour_name: str | None = None
    infra_name: str | None = None
    trace_cache_dir: Path | None = None
    data_cache_dir: Path | None = None
    strategy: str | None = None
    step_overrides: list = field(default_factory=list)
    clean_stale: bool | None = None


def _is_mas_experiment_yaml(experiment_yaml: Path) -> bool:
    """Detect MAS experiment schema without loading full lab config."""
    try:
        from mas.runtime.spec.source import load_yaml_file

        data = load_yaml_file(experiment_yaml)
    except OSError:
        return False
    if not isinstance(data, dict):
        return False
    exp = data.get("experiment", data)
    if not isinstance(exp, dict):
        return False
    if exp.get("mas") is not None or data.get("mas") is not None:
        return False
    apps = exp.get("applications")
    if isinstance(apps, list) and apps:
        return True
    kind = str(data.get("kind", "") or exp.get("kind", "")).lower()
    return kind in {"mas-experiment", "mas.experiment"}


async def run_benchmark(
    experiment_yaml: Path,
    options: BenchmarkRunOptions | None = None,
) -> bool:
    opts = options or BenchmarkRunOptions()

    if not experiment_yaml.exists():
        logger.error("Experiment YAML not found: %s", experiment_yaml)
        return False

    if opts.benchmark_id or opts.resume:
        from mas.lab.benchmark.schedule.resume import resume_mas_benchmark

        return await resume_mas_benchmark(
            experiment_yaml=experiment_yaml,
            benchmark_id=opts.benchmark_id,
            progress=opts.progress,
            force_lock=opts.force_lock,
        )

    if not _is_mas_experiment_yaml(experiment_yaml):
        logger.error(
            "Unsupported experiment schema in %s — declare experiment.applications "
            "(see docs/manifests/experiment.md).",
            experiment_yaml,
        )
        return False

    logger.info("MAS experiment schema detected — routing to MAS benchmark runner")
    from mas.lab.benchmark.schedule.run_batch import run_mas_benchmark

    return await run_mas_benchmark(
        experiment_yaml=experiment_yaml,
        progress=opts.progress,
        dry_run=opts.dry_run,
        max_runs=opts.max_runs,
        limit_scenarios=opts.limit_scenarios,
        single_run=opts.single_run,
        flavour_name=opts.flavour_name,
        infra_name=opts.infra_name,
        force=opts.force,
        trace_cache_dir=opts.trace_cache_dir,
        data_cache_dir=opts.data_cache_dir,
        output_dir=opts.output_dir,
        strategy=opts.strategy,
        step_overrides=opts.step_overrides,
        clean_stale=opts.clean_stale,
    )


async def restart_mas_run(
    *,
    run_dir: Path,
    experiment_yaml: Path,
    run_id: str,
    progress: bool = True,
) -> bool:
    """Clear one run's traces and re-invoke the MAS batch loop."""
    import re
    import shutil

    match = re.match(r"^(.+)__item(.+)__r(\d+)$", run_id)
    if not match:
        raise ValueError(
            f"Invalid MAS run_id {run_id!r} — expected "
            "'{{scenario}}__item{{id}}__r{{n}}'"
        )

    scenario_id, item_id, run_num = match.groups()
    from mas.lab.lab.config import MASExperimentConfig

    exp = MASExperimentConfig.from_yaml(experiment_yaml)
    sc_spec = exp.get_scenario(scenario_id)
    sc_dir = sc_spec.output_dir_name if sc_spec else scenario_id
    run_output_dir = run_dir / sc_dir / f"item{item_id}" / f"r{run_num}"
    trace_dir = run_output_dir / "traces"

    if trace_dir.exists():
        shutil.rmtree(trace_dir)
    elif run_output_dir.exists():
        shutil.rmtree(run_output_dir)

    from mas.lab.benchmark.schedule.run_batch import run_mas_benchmark

    return await run_mas_benchmark(
        experiment_yaml=experiment_yaml,
        progress=progress,
        output_dir=run_dir,
        force=False,
    )
