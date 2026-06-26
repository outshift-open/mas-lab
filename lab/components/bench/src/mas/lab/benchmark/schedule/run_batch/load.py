#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Load and validate a MAS experiment for batch execution."""

import logging
import sys as _sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mas.lab.benchmark.execution import parse_step_overrides
from mas.lab.benchmark.schedule.pipeline_resolve import resolve_pipeline_specs

logger = logging.getLogger(__name__)


@dataclass
class LoadedExperiment:
    """Configuration resolved from experiment YAML before execution."""

    exp: Any
    experiment_yaml: Path
    configs_dir: Optional[Path]
    scenario_ids: list[str]
    dataset_items: list
    pipeline_specs: list
    step_overrides_dict: dict
    flavour: Any
    flavour_name: str
    infra_name: Optional[str]
    n_runs: int
    trace_cache_dir: Optional[Path]


def load_experiment(
    experiment_yaml: Path,
    *,
    max_runs: Optional[int] = None,
    limit_scenarios: Optional[int] = None,
    single_run: bool = False,
    flavour_name: Optional[str] = None,
    infra_name: Optional[str] = None,
    trace_cache_dir: Optional[Path] = None,
    step_overrides: Optional[list] = None,
) -> LoadedExperiment | None:
    """Load MASExperimentConfig and resolve scenarios, dataset, flavour."""
    try:
        from mas.lab.lab.config import MASExperimentConfig
    except ImportError as exc:
        logger.error(f"Cannot import MASExperimentConfig: {exc}")
        return None

    logger.info(f"Loading MAS experiment: {experiment_yaml}")
    try:
        exp = MASExperimentConfig.from_yaml(experiment_yaml)
    except Exception as exc:
        logger.error(f"Failed to load MAS experiment YAML: {exc}")
        return None

    try:
        from mas.runtime.spec.source import load_yaml_file
        from mas.lab.manifests.validator import (
            ManifestValidationError,
            validate_manifest,
        )

        raw = load_yaml_file(experiment_yaml)
        validate_manifest(
            raw,
            source=str(experiment_yaml),
            kind="experiment",
            base_dir=experiment_yaml.parent,
        )
    except ManifestValidationError as exc:
        logger.error("Experiment manifest validation failed: %s", exc)
        return None
    except Exception as exc:
        logger.error("Experiment manifest validation error: %s", exc)
        return None

    from mas.lab.lab.config import discover_lab_context, inject_lab_libraries

    inject_lab_libraries(discover_lab_context(experiment_yaml))

    _lab_dir = str(experiment_yaml.parent)
    if _lab_dir not in _sys.path:
        _sys.path.insert(0, _lab_dir)

    try:
        from mas.lab.workspace import WorkspaceConfig as _WsCfg
        _ws_libs = _WsCfg.load(experiment_yaml.parent)
        if _ws_libs.found:
            for _lib_rel in (_ws_libs._data.get("libraries") or []):
                _lib_abs = str((_ws_libs._path / _lib_rel).resolve())
                if _lib_abs not in _sys.path:
                    _sys.path.append(_lib_abs)
                    logger.debug("Library path added to sys.path: %s", _lib_abs)
    except Exception:
        logger.debug('suppressed', exc_info=True)

    _step_overrides_dict = parse_step_overrides(step_overrides)
    if _step_overrides_dict:
        logger.info("CLI step overrides: %s", _step_overrides_dict)

    logger.info(f"MAS Experiment: {exp.name}")
    logger.info(f"  Description: {exp.description}")

    trace_cache_dir = trace_cache_dir or getattr(exp, "trace_cache_dir", None)

    if not flavour_name and exp.default_flavour:
        flavour_name = exp.default_flavour
        logger.info(f"Using default flavour from experiment: {flavour_name}")
    if not flavour_name:
        flavour_name = "local"

    _flavour = None
    if flavour_name:
        try:
            from mas.lab.flavour.load import load_flavour as _load_flavour
            from mas.lab.flavour.resolve import resolve_flavour_path

            _fpath = resolve_flavour_path(flavour_name)
            _flavour = _load_flavour(_fpath)
            logger.info(
                "Flavour: %s (mas-library-standard: %s)",
                _flavour.get("metadata", {}).get("name", flavour_name),
                _fpath,
            )
        except FileNotFoundError as _fe:
            logger.error("%s", _fe)
            return None
        except Exception as _fe:
            logger.warning("Failed to load flavour '%s': %s", flavour_name, _fe)

    if not infra_name:
        infra_name = getattr(exp, "default_infra", None) or None
    if infra_name:
        logger.info("Using infra bundle: %s", infra_name)

    configs_dir: Optional[Path]
    if exp.mas and exp.mas.configs_dir:
        configs_dir = exp.mas.configs_dir
    elif exp.mas and exp.mas.manifest:
        configs_dir = exp.mas.manifest.parent / "overlays"
    else:
        configs_dir = experiment_yaml.parent / "overlays"

    scenario_ids = exp.scenario_ids()
    if not scenario_ids:
        if not configs_dir.is_dir():
            logger.error(f"configs_dir not found: {configs_dir}")
            return None
        from mas.lab.lab.config import discover_scenario_stems
        scenario_ids = discover_scenario_stems(configs_dir)
        if not scenario_ids:
            logger.error(f"No scenarios found under {configs_dir}")
            return None
    elif not configs_dir.is_dir():
        logger.debug(f"configs_dir not found: {configs_dir} — no overlay files (scenarios explicitly declared)")
        configs_dir = None

    _pipeline_specs = resolve_pipeline_specs(exp, experiment_yaml)
    dataset_items = _load_dataset_items(exp)

    if exp.dataset_filter:
        _before = len(dataset_items)
        dataset_items = [
            item for item in dataset_items
            if all(item.get(k) == v for k, v in exp.dataset_filter.items())
        ]
        logger.info(f"Dataset filter {exp.dataset_filter}: {_before} → {len(dataset_items)} items")

    if exp.dataset_limit is not None and len(dataset_items) > exp.dataset_limit:
        dataset_items = dataset_items[:exp.dataset_limit]
        logger.info(f"Dataset limit: capped to {exp.dataset_limit} items")

    n_runs = max_runs if max_runs is not None else exp.execution.n_runs if exp.execution else 1
    if single_run:
        limit_scenarios = 1
        n_runs = 1
        dataset_items = dataset_items[:1]
    if limit_scenarios is not None:
        scenario_ids = scenario_ids[:limit_scenarios]

    total = len(scenario_ids) * len(dataset_items) * n_runs
    logger.info(f"  Scenarios : {len(scenario_ids)}, items: {len(dataset_items)}, runs: {n_runs} = {total} total")

    return LoadedExperiment(
        exp=exp,
        experiment_yaml=experiment_yaml,
        configs_dir=configs_dir,
        scenario_ids=scenario_ids,
        dataset_items=dataset_items,
        pipeline_specs=_pipeline_specs,
        step_overrides_dict=_step_overrides_dict,
        flavour=_flavour,
        flavour_name=flavour_name,
        infra_name=infra_name,
        n_runs=n_runs,
        trace_cache_dir=trace_cache_dir,
    )


def _load_dataset_items(exp: Any) -> list:
    dataset_items: list = []
    if exp.dataset and exp.dataset.exists():
        try:
            from mas.runtime.spec.source import load_yaml_file

            ds_data = load_yaml_file(exp.dataset)
            if isinstance(ds_data, dict):
                dataset_items = (
                    ds_data.get("spec", {}).get("items")
                    or ds_data.get("items")
                    or []
                )
            else:
                dataset_items = ds_data
            logger.info(f"Dataset: {exp.dataset} ({len(dataset_items)} items)")
        except Exception as exc:
            logger.warning(f"Failed to load dataset {exp.dataset}: {exc}")
    elif exp.dataset:
        logger.warning(f"Dataset not found: {exp.dataset}")

    if not dataset_items:
        dataset_items = [
            {
                "id": 0,
                "inputs": {
                    "user": [{"role": "user", "content": "Triage an SRE incident."}],
                },
            }
        ]
        logger.warning("No dataset items loaded; using default prompt")
    return dataset_items


def print_dry_run(loaded: LoadedExperiment) -> None:
    """Print dry-run summary to stdout."""
    exp = loaded.exp
    total = len(loaded.scenario_ids) * len(loaded.dataset_items) * loaded.n_runs
    print()
    print("=" * 70)
    print("DRY RUN — MAS Benchmark Configuration")
    print("=" * 70)
    print(f"Experiment : {exp.name}")
    if exp.mas and exp.mas.manifest:
        print(f"Manifest   : {exp.mas.manifest}")
    print(f"configs_dir: {loaded.configs_dir}")
    print(f"Scenarios  : {loaded.scenario_ids}")
    print(f"Dataset    : {len(loaded.dataset_items)} items")
    print(f"Runs/test  : {loaded.n_runs}")
    print(f"Total      : {total} executions")
    _pipeline_specs = loaded.pipeline_specs
    if exp.is_v2:
        _all_steps = _pipeline_specs
        _by_scope: dict = {}
        for s in _all_steps:
            _by_scope.setdefault(s.scope, []).append(s)
        _parts = []
        for scope in ("run", "test", "scenario", "experiment"):
            count = len(_by_scope.get(scope, []))
            if count:
                _parts.append(f"{count} {scope}")
        print(f"Pipeline   : {len(_all_steps)} steps ({', '.join(_parts)})")
    elif _pipeline_specs:
        _pipe = _pipeline_specs
        _ps_count = sum(1 for s in _pipe if getattr(s, "per_scenario", False))
        _scalar_count = len(_pipe) - _ps_count
        print(f"Pipeline   : {len(_pipe)} steps "
              f"({_ps_count} per-scenario × {len(loaded.scenario_ids)} = "
              f"{_ps_count * len(loaded.scenario_ids)} + {_scalar_count} scalar)")
    print("=" * 70)
    print("\n✓ Configuration valid — ready to run")
