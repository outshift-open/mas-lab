#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Load experiment pipeline steps into memory — inline, ref, app, or sibling file.

After :func:`resolve_pipeline_specs`, execution is identical regardless of source.
Uses :mod:`mas.runtime.spec.source` for path / app resolution (same as other manifests).
"""

import logging
from pathlib import Path
from typing import Any

from mas.runtime.spec.source import resolve_app_resource, resolve_yaml_path

logger = logging.getLogger(__name__)


def resolve_pipeline_specs(exp: Any, experiment_yaml: Path) -> list:
    """Return all pipeline step specs for an experiment (may be empty).

    Resolution order (first non-empty wins):

    1. Experiment manifest — ``all_pipeline_steps()`` (v2 levels + flat ``pipeline:``)
    2. External ref — ``pipeline_ref`` or ``pipeline: path/to.yaml`` (string)
    3. App bundle — ``pipeline_app`` (``{app: name, name: pipeline}``)
    4. Sibling file — ``pipeline.yaml`` next to the experiment file
    """
    specs = _specs_from_experiment(exp)
    if specs:
        return specs

    ref_path = _pipeline_ref_path(exp, experiment_yaml)
    if ref_path is not None:
        return _load_specs_from_yaml(ref_path)

    app_ref = getattr(exp, "pipeline_app", None)
    if isinstance(app_ref, dict) and app_ref.get("app"):
        try:
            return _load_specs_from_yaml(resolve_app_resource(app_ref))
        except FileNotFoundError as exc:
            logger.warning("%s", exc)
            return []

    sibling = experiment_yaml.parent / "pipeline.yaml"
    if sibling.is_file():
        return _load_specs_from_yaml(sibling)

    return []


def resolve_pipeline_specs_from_yaml(path: Path) -> list:
    """Load step specs from a standalone pipeline YAML file."""
    return _load_specs_from_yaml(path)


def _specs_from_experiment(exp: Any) -> list:
    if hasattr(exp, "all_pipeline_steps"):
        steps = exp.all_pipeline_steps()
        if steps:
            return list(steps)
    pipeline = getattr(exp, "pipeline", None) or []
    if isinstance(pipeline, list) and pipeline:
        return list(pipeline)
    return []


def _pipeline_ref_path(exp: Any, experiment_yaml: Path) -> Path | None:
    raw_ref = getattr(exp, "pipeline_ref", None)
    if isinstance(raw_ref, str) and raw_ref.strip():
        return _resolve_existing_path(raw_ref.strip(), experiment_yaml.parent)
    raw = getattr(exp, "pipeline", None)
    if isinstance(raw, str) and raw.strip():
        return _resolve_existing_path(raw.strip(), experiment_yaml.parent)
    return None


def _resolve_existing_path(ref: str, anchor: Path) -> Path | None:
    try:
        path = resolve_yaml_path(ref, anchor)
    except FileNotFoundError:
        return None
    return path


def _load_specs_from_yaml(path: Path) -> list:
    from mas.lab.benchmark.pipeline import Pipeline
    from mas.lab.lab.config import PipelineStepSpec

    try:
        step_dicts = Pipeline.step_dicts_from_yaml(path)
    except Exception as exc:
        logger.warning("Failed to load pipeline from %s: %s", path, exc)
        return []

    specs: list[PipelineStepSpec] = []
    for step_data in step_dicts:
        specs.append(
            PipelineStepSpec.from_dict(
                {
                    "name": step_data["name"],
                    "type": step_data["type"],
                    "phase": step_data.get("phase", "post"),
                    "per_scenario": bool(step_data.get("per_scenario", False)),
                    "per_run": bool(step_data.get("per_run", False)),
                    "config": dict(step_data.get("config", {})),
                    "depends_on": list(step_data.get("depends_on", [])),
                }
            )
        )
    return specs


def spec_to_step_dict(spec: Any) -> dict:
    """Normalise a :class:`PipelineStepSpec` to executor step dict."""
    return {
        "name": spec.name or spec.type,
        "type": spec.type,
        "phase": getattr(spec, "phase", "post"),
        "config": dict(spec.config or {}),
        "depends_on": list(spec.depends_on or []),
    }
