#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""MAS experiment metadata helpers for the batch scheduler."""

from pathlib import Path

from mas.lab.benchmark.metadata import BenchmarkMetadata, BenchmarkStatus

def register_mas_run(
    output_dir: Path,
    experiment_yaml: Path,
    exp,
) -> "BenchmarkMetadata":
    """Create or load a metadata.yaml in *output_dir* for MAS run tracking.

    For MAS experiments the output_dir is fixed per experiment YAML, so the
    same metadata.yaml is reused across all runs (stable benchmark_id).
    """
    import uuid as _uuid
    from datetime import datetime

    metadata_path = output_dir / "metadata.yaml"
    if metadata_path.exists():
        try:
            return BenchmarkMetadata.from_yaml(metadata_path)
        except Exception:
            logger.debug('suppressed', exc_info=True)
    metadata = BenchmarkMetadata(
        benchmark_id=str(_uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        experiment_name=exp.name,
        experiment_description=getattr(exp, "description", ""),
        experiment_yaml_path=str(experiment_yaml.resolve()),
        status=BenchmarkStatus.RUNNING,
        total_scenarios=0,
        started_at=datetime.now().isoformat(),
        run_dir=str(output_dir),
        results_file=str(output_dir / "results.csv"),
        plots_dir=str(output_dir / "plots"),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata.to_yaml(metadata_path)
    return metadata


def execution_as_dict(exp) -> dict:
    """Serialize experiment execution block for plan builder."""
    import dataclasses

    execution = getattr(exp, "execution", None)
    if execution is None:
        return {}
    if isinstance(execution, dict):
        return execution
    raw = getattr(exp, "_raw", None) or {}
    if isinstance(raw, dict):
        block = (raw.get("experiment") or raw).get("execution")
        if isinstance(block, dict):
            return block
    if dataclasses.is_dataclass(execution):
        return dataclasses.asdict(execution)
    return {}


