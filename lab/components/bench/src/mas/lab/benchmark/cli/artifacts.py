#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""List artifacts declared in an experiment, with generated vs missing status."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from mas.lab.benchmark.cli.declared import (
    ArtifactSlot,
    catalog_from_yaml,
    display_level,
    plan_artifacts,
)

logger = logging.getLogger(__name__)

_TARGET_ERR = "TARGET must be last, a benchmark id, or an experiment YAML"


def _job_from_run(
    label: str, result: tuple[object, Path]
) -> tuple[list[tuple[Path, Path | None]], str | None]:
    metadata, run_dir = result
    yaml_path = getattr(metadata, "experiment_yaml_path", None)
    if not yaml_path:
        return [], f"Run {label} has no experiment.yaml path."
    return [(Path(yaml_path), run_dir)], None


def format_artifact_list(
    slots: Sequence[ArtifactSlot],
    *,
    level_filter: str | None = None,
    verbose: bool = False,
) -> list[str]:
    """Format declared artifacts and whether each file exists."""
    want_level = display_level(level_filter) if level_filter else None
    rows = [
        s for s in slots
        if want_level is None or display_level(s.level) == want_level
    ]
    if not rows:
        return ["Artifacts: (none declared)"]

    n_ok = sum(1 for s in rows if s.generated)
    n_miss = len(rows) - n_ok
    name_w = max(len(s.name) for s in rows)
    type_w = max(len(s.type) for s in rows)
    loc_w = max((len(s.location or ".") for s in rows), default=1)
    lines = [f"Artifacts ({n_ok} generated, {n_miss} missing):"]
    for slot in rows:
        loc = slot.location or "."
        dl = display_level(slot.level)
        rel = slot.spec.relative_path()
        if slot.generated:
            size_kb = slot.path.stat().st_size / 1024
            status = f"generated  {size_kb:.1f} KB"
        else:
            status = "missing"
        row = (
            f"  {dl:<12} {loc:<{loc_w}}  {slot.name:<{name_w}}  "
            f"{slot.type:<{type_w}}  {rel}  {status}"
        )
        if verbose and slot.spec.description:
            row = f"{row}  — {slot.spec.description}"
        lines.append(row)
    return lines


def artifact_list_command(args) -> int:
    """List artifacts from the experiment spec, marking generated vs missing."""
    jobs, err = _resolve_jobs(args)
    if err:
        logger.error(err)
        return 1
    type_filter = getattr(args, "artifact_type", None)
    level_filter = getattr(args, "level", None)
    verbose = bool(getattr(args, "verbose", False))
    multi = len(jobs) > 1
    for yaml_path, data_dir in jobs:
        catalog = catalog_from_yaml(yaml_path)
        if multi or verbose:
            print(f"# {yaml_path}")
            if data_dir is not None:
                print(f"# {data_dir}")
        root = data_dir if data_dir is not None else Path()
        slots = plan_artifacts(root, catalog, type_filter=type_filter)
        for line in format_artifact_list(
            slots, level_filter=level_filter, verbose=verbose
        ):
            print(line)
        if multi:
            print()
    return 0


def _resolve_jobs(args) -> tuple[list[tuple[Path, Path | None]], str | None]:
    target = getattr(args, "target", None)
    if not target:
        return [], f"{_TARGET_ERR}."
    if target in ("last", "latest"):
        result = _last_run()
        if result is None:
            return [], "No last benchmark run."
        return _job_from_run("last", result)

    path = Path(target)
    if path.is_dir():
        return [], f"{_TARGET_ERR}, not a directory."
    if path.is_file() and path.suffix in {".yaml", ".yml"}:
        return [(path, _output_dir_for(path))], None

    found = _run_manager().get_run(target)
    if found is not None:
        return _job_from_run(target, found)
    return [], f"{_TARGET_ERR}: {target}"


def _output_dir_for(yaml_path: Path) -> Path | None:
    yaml_path = yaml_path.resolve()
    last = _last_run()
    if last is not None:
        metadata, run_dir = last
        stored = getattr(metadata, "experiment_yaml_path", None)
        if stored:
            try:
                if Path(stored).resolve() == yaml_path:
                    return run_dir
            except OSError:
                pass
    try:
        found = _run_manager().get_last_run_for_experiment(yaml_path)
    except Exception:
        found = None
    if found is not None:
        return found[1]
    try:
        from mas.lab.lab.config import MASExperimentConfig

        exp = MASExperimentConfig.from_yaml(yaml_path)
    except Exception:
        return None
    dd = getattr(exp, "output_dir", None)
    return Path(dd) if dd else None


def _run_manager():
    from mas.lab.benchmark.run_manager import BenchmarkRunManager

    return BenchmarkRunManager()


def _last_run():
    return _run_manager().get_last_run()
