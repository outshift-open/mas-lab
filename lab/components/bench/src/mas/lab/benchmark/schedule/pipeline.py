#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Batch pipeline orchestration — resolve once, materialize, execute."""

import copy
import logging
from pathlib import Path
from typing import Any, Optional

from mas.lab.benchmark.execution import apply_step_overrides
from mas.lab.benchmark.schedule.run_discovery import discover_benchmark_runs
from mas.lab.benchmark.schedule.pipeline_resolve import (
    resolve_pipeline_specs,
    spec_to_step_dict,
)

logger = logging.getLogger(__name__)

_INFRA_STEP_TYPES = frozenset(
    {"service_start", "service_stop", "serialize", "deserialize"}
)


def substitute_template_vars(obj: Any, template_vars: dict[str, str]) -> Any:
    """Replace ``{key}`` placeholders in nested config structures."""
    if isinstance(obj, str):
        out = obj
        for key, value in template_vars.items():
            out = out.replace(f"{{{key}}}", value)
        return out
    if isinstance(obj, dict):
        return {k: substitute_template_vars(v, template_vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_template_vars(v, template_vars) for v in obj]
    return obj


def _base_step_name(spec: Any) -> str:
    return spec.name or spec.type


def _expand_depends_on(
    depends_on: list[str],
    scenario_id: str,
    per_scenario_names: set[str],
    *,
    run_suffix: str | None = None,
    per_run_names: set[str] | None = None,
) -> list[str]:
    expanded: list[str] = []
    per_run_names = per_run_names or set()
    for dep in depends_on or []:
        if run_suffix and dep in per_run_names:
            expanded.append(f"{dep}-{run_suffix}")
        elif dep in per_scenario_names:
            expanded.append(f"{dep}-{scenario_id}")
        else:
            expanded.append(dep)
    return expanded


def _run_step_suffix(scenario: str, test: str, run: str) -> str:
    return f"{scenario}-{test}-{run}"


def materialize_step_dicts(
    specs: list,
    *,
    phase: str | None = None,
    scenario_ids: list[str],
    infra_name: Optional[str],
    step_overrides: Optional[dict],
    template_vars: Optional[dict[str, str]] = None,
) -> list[dict]:
    """Expand specs (per-scenario, infra, overrides) and optionally filter by ``phase``."""
    phase_specs = (
        [s for s in specs if getattr(s, "phase", "post") == phase]
        if phase is not None
        else list(specs)
    )
    if not phase_specs:
        return []

    per_scenario_names = {
        _base_step_name(s) for s in phase_specs if getattr(s, "per_scenario", False)
    }
    per_run_names = {
        _base_step_name(s) for s in phase_specs if getattr(s, "per_run", False)
    }
    step_dicts: list[dict] = []
    tmpl = template_vars or {}
    output_dir = Path(tmpl.get("output_dir", "."))

    for spec in phase_specs:
        base_name = _base_step_name(spec)
        is_per_scenario = getattr(spec, "per_scenario", False)
        is_per_run = getattr(spec, "per_run", False)

        if is_per_run:
            scenario_filter = scenario_ids if is_per_scenario else None
            run_targets = []
            if is_per_scenario:
                for sid in scenario_ids:
                    run_targets.extend(
                        discover_benchmark_runs(output_dir, scenario=sid)
                    )
            else:
                run_targets = discover_benchmark_runs(output_dir)

            for run_ref in run_targets:
                cfg = copy.deepcopy(spec.config or {})
                cfg.setdefault("scenario", run_ref.scenario)
                cfg.setdefault("test", run_ref.test)
                cfg.setdefault("run", run_ref.run)
                cfg.setdefault("run_dir", str(run_ref.path))
                cfg.setdefault("scenario_dir", str(output_dir / run_ref.scenario))
                if infra_name and spec.type in _INFRA_STEP_TYPES:
                    cfg.setdefault("infra", infra_name)

                cfg = apply_step_overrides(cfg, spec.type, step_overrides or {})
                if tmpl:
                    cfg = substitute_template_vars(cfg, tmpl)
                suffix = _run_step_suffix(run_ref.scenario, run_ref.test, run_ref.run)
                name = f"{base_name}-{suffix}"
                deps = _expand_depends_on(
                    list(spec.depends_on or []),
                    run_ref.scenario,
                    per_scenario_names,
                    run_suffix=suffix,
                    per_run_names=per_run_names,
                )
                step_dicts.append(
                    {
                        "name": name,
                        "type": spec.type,
                        "phase": getattr(spec, "phase", "post"),
                        "config": cfg,
                        "depends_on": deps,
                    }
                )
            continue

        targets = scenario_ids if is_per_scenario else [None]

        for sid in targets:
            cfg = copy.deepcopy(spec.config or {})
            if sid is not None:
                cfg.setdefault("scenario", sid)
                cfg.setdefault("scenarios", [sid])
                if tmpl.get("output_dir"):
                    cfg.setdefault("scenario_dir", f"{tmpl['output_dir']}/{sid}")
            if infra_name and spec.type in _INFRA_STEP_TYPES:
                cfg.setdefault("infra", infra_name)

            cfg = apply_step_overrides(cfg, spec.type, step_overrides or {})
            if tmpl:
                cfg = substitute_template_vars(cfg, tmpl)
            name = f"{base_name}-{sid}" if sid is not None else base_name
            deps = (
                _expand_depends_on(
                    list(spec.depends_on or []),
                    sid,
                    per_scenario_names,
                    per_run_names=per_run_names,
                )
                if sid is not None
                else list(spec.depends_on or [])
            )
            step_dicts.append(
                {
                    "name": name,
                    "type": spec.type,
                    "phase": getattr(spec, "phase", "post"),
                    "config": cfg,
                    "depends_on": deps,
                }
            )
    return step_dicts


def build_runtime_pipeline(
    *,
    exp: Any,
    experiment_yaml: Path,
    step_dicts: list[dict],
    pipeline_name: str | None = None,
):
    from mas.lab.benchmark.pipeline import (
        Pipeline,
        PipelineConfig,
        PipelineStep,
    )

    steps = [
        PipelineStep.from_dict(s, base_dir=experiment_yaml.parent)
        for s in step_dicts
    ]
    label = pipeline_name or getattr(exp, "name", "pipeline")
    return Pipeline(
        config=PipelineConfig(name=label),
        steps=steps,
        config_path=experiment_yaml,
    )


class PipelineExecutionError(RuntimeError):
    """Raised when a benchmark post/pre pipeline step fails."""


async def execute_runtime_pipeline(
    pipeline,
    *,
    output_dir: Path,
    progress: bool = True,
    data_cache_dir: Optional[Path] = None,
    template_vars: Optional[dict[str, str]] = None,
    force_rerun: list[str] | None = None,
    phase_label: str = "",
) -> bool:
    from mas.lab.benchmark.pipeline.executor import PipelineExecutor

    if phase_label == "post":
        extract_fp = output_dir / ".cache" / "extract.fingerprint"
        if extract_fp.exists():
            extract_fp.unlink()

    if pipeline.steps:
        print()
        title = f"{phase_label}-phase" if phase_label else "pipeline"
        print(f"Running {title} ({len(pipeline.steps)} steps):")
        for ps in pipeline.steps:
            print(f"  · {ps.name} ({ps.type})")

    executor = PipelineExecutor(
        pipeline,
        output_dir=output_dir,
        progress=progress,
        data_cache_dir=data_cache_dir,
    )
    try:
        result = await executor.run(
            template_vars=dict(template_vars or {"output_dir": str(output_dir)}),
            force_rerun=force_rerun,
        )
        print(result.summary())
        if not result.success:
            raise PipelineExecutionError(
                f"{phase_label or 'pipeline'} failed — see step errors above"
            )
        return True
    except PipelineExecutionError:
        raise
    except Exception as exc:
        logger.error("Pipeline execution failed: %s", exc)
        raise PipelineExecutionError(str(exc)) from exc


def _load_generated_dataset(output_dir: Path) -> list | None:
    gen_ds_path = output_dir / "generated_dataset.yaml"
    if not gen_ds_path.exists():
        return None
    try:
        from mas.runtime.spec.source import load_yaml_file

        gds_data = load_yaml_file(gen_ds_path)
        gen_items = (
            gds_data.get("items", [])
            if isinstance(gds_data, dict)
            else gds_data
        )
        if gen_items:
            logger.info(
                "Pre-phase: loaded %d generated dataset items from %s",
                len(gen_items),
                gen_ds_path,
            )
            return gen_items
    except Exception as gds_exc:
        logger.warning("Failed to load generated_dataset.yaml: %s", gds_exc)
    return None


async def run_pipeline_phase(
    *,
    phase: str,
    exp: Any,
    experiment_yaml: Path,
    output_dir: Path,
    specs: list | None = None,
    scenario_ids: list[str] | None = None,
    infra_name: Optional[str] = None,
    step_overrides: Optional[dict] = None,
    progress: bool = True,
    data_cache_dir: Optional[Path] = None,
) -> list | None:
    """Run all steps for ``phase`` (``pre`` or ``post``).

    Returns updated dataset items when ``phase=='pre'`` and a generator step
    wrote ``generated_dataset.yaml``; otherwise ``None``.
    """
    resolved = specs if specs is not None else resolve_pipeline_specs(exp, experiment_yaml)
    step_dicts = materialize_step_dicts(
        resolved,
        phase=phase,
        scenario_ids=list(scenario_ids or []),
        infra_name=infra_name,
        step_overrides=step_overrides,
        template_vars={"output_dir": str(output_dir)},
    )
    if not step_dicts:
        return None

    pipeline = build_runtime_pipeline(
        exp=exp,
        experiment_yaml=experiment_yaml,
        step_dicts=step_dicts,
        pipeline_name=f"{exp.name}-{phase}",
    )
    ok = await execute_runtime_pipeline(
        pipeline,
        output_dir=output_dir,
        progress=progress,
        data_cache_dir=data_cache_dir,
        phase_label=phase,
    )
    if phase == "pre" and ok:
        return _load_generated_dataset(output_dir)
    return None


def materialize_selected_specs(
    specs: list,
    *,
    experiment_yaml: Path,
    output_dir: Path,
    step_overrides: Optional[dict] = None,
    name_overrides: Optional[dict] = None,
) -> list[dict]:
    """Materialize an explicit subset of specs (standalone ``mas-lab run pipeline step``)."""
    step_dicts = materialize_step_dicts(
        specs,
        phase=None,
        scenario_ids=[],
        infra_name=None,
        step_overrides=step_overrides,
        template_vars={"output_dir": str(output_dir)},
    )
    for step_dict in step_dicts:
        extra = (name_overrides or {}).get(step_dict["name"], {})
        if extra:
            step_dict["config"].update(extra)
    return step_dicts
