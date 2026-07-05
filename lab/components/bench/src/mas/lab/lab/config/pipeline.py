#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class PipelineStepSpec:
    """Specification for a single step in an inline experiment pipeline.

    Inline pipeline steps are declared inside the ``pipeline:`` section of
    an experiment YAML and are expanded / executed automatically after the
    benchmark run completes.

    **v1 format** — flat list with ``per_scenario: true``:

    .. code-block:: yaml

        pipeline:
          - name: extract
            type: extract_trajectories
            per_scenario: true

    **v2 format** — level-scoped with ``in:``/``out:`` artifact references:

    .. code-block:: yaml

        run:
          pipeline:
            - name: stats
              type: extract_trace_stats
              in: trace
              out: metrics

    Both formats are supported.  v2 is detected when the experiment YAML
    contains ``run:``, ``test:``, or ``scenario:`` level sections.
    """

    type: str
    """Step type key (e.g. ``eval_mce``, ``processor``, ``extract_trajectories``)."""

    name: Optional[str] = None
    """Optional explicit step name.  Auto-generated when absent."""

    per_scenario: bool = False
    """(v1) When True, expand this step once for each scenario."""

    per_run: bool = False
    """(v1) When True, expand this step once for each benchmark run folder."""

    phase: str = "post"
    """Execution phase: ``pre`` (before benchmark loop) or ``post`` (after)."""

    scope: str = ""
    """Execution scope assigned by the level section (``run``, ``test``,
    ``scenario``, ``experiment``).  In v1, set explicitly or inferred
    from ``per_scenario``."""

    config: Dict[str, Any] = field(default_factory=dict)
    """Step-type-specific configuration (merged with injected template vars)."""

    depends_on: List[str] = field(default_factory=list)
    """Names of steps that must complete before this step runs."""

    inputs: List[str] = field(default_factory=list)
    """(v2) Input artifact names.  When a step at level L references an
    artifact from level L-1, it fans in all instances."""

    outputs: List[str] = field(default_factory=list)
    """(v2) Output artifact names.  Must match artifacts declared at the
    step's level."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineStepSpec":
        # Parse in/out — accept scalar or list
        raw_in = data.get("in", [])
        inputs = [raw_in] if isinstance(raw_in, str) else list(raw_in)
        raw_out = data.get("out", [])
        outputs = [raw_out] if isinstance(raw_out, str) else list(raw_out)

        return cls(
            type=data["type"],
            name=data.get("name"),
            per_scenario=data.get("per_scenario", False),
            per_run=data.get("per_run", False),
            phase=data.get("phase", "post"),
            scope=data.get("scope", ""),
            config=data.get("config", {}),
            depends_on=data.get("depends_on", []),
            inputs=inputs,
            outputs=outputs,
        )


# ---------------------------------------------------------------------------
# ArtifactSpec — named data product at a hierarchy level
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Artifact type registry
# ---------------------------------------------------------------------------

# Default path templates keyed by artifact type.
# Users can register custom types via ``register_artifact_type()``.
_ARTIFACT_TYPE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "trace": {
        "path": "{run_dir}/traces/events.jsonl",
        "format": "jsonl",
        "description": "Raw observability event stream from a single run.",
    },
    "run_info": {
        "path": "{run_dir}/run_info.json",
        "format": "json",
        "description": "Run metadata (hash, model, timing, status).",
    },
    "metrics": {
        "path": "{level_dir}/metrics.json",
        "format": "json",
        "schema": "artefacts/metrics.schema.json",
        "description": "Quality metrics computed by evaluation providers.",
    },
    "dataframe": {
        "path": "{level_dir}/data.csv",
        "format": "csv",
        "description": "Tidy CSV dataframe for analysis and plotting.",
    },
    "plot": {
        "path": "{level_dir}/plot.png",
        "format": "png",
        "description": "Visualization output (PNG, SVG, HTML, or PDF).",
    },
}

# Keep backward compat alias
_ARTIFACT_DEFAULT_PATHS: Dict[str, str] = {
    k: v["path"] for k, v in _ARTIFACT_TYPE_REGISTRY.items()
}


def register_artifact_type(
    name: str,
    path: str,
    format: str = "json",
    description: str = "",
    schema: Optional[str] = None,
) -> None:
    """Register a custom artifact type.

    Custom types can then be referenced in experiment YAML::

        artifacts:
            my_data: my_custom_type

    Args:
        name: Type identifier (e.g. ``"embeddings"``).
        path: Default path template with ``{run_dir}``/``{level_dir}`` vars.
        format: File format hint (``json``, ``csv``, ``jsonl``, ``parquet``, ``png``).
        description: Human-readable description.
        schema: Optional JSON schema path for validation.
    """
    _ARTIFACT_TYPE_REGISTRY[name] = {
        "path": path,
        "format": format,
        "description": description,
        **({"schema": schema} if schema else {}),
    }
    _ARTIFACT_DEFAULT_PATHS[name] = path


def list_artifact_types() -> Dict[str, Dict[str, Any]]:
    """Return all registered artifact types."""
    return dict(_ARTIFACT_TYPE_REGISTRY)


@dataclass
class ArtifactSpec:
    """A named, typed data product declared at a hierarchy level.

    Artifacts can be declared in short form (``name: type``) or long form:

    .. code-block:: yaml

        artifacts:
          metrics: metrics                    # short
          trajectory:                      # long
            type: plot
            path: "{run_dir}/trajectory.html"
            validate: true

    Built-in artifacts ``trace`` and ``run_info`` are auto-created by the
    execution engine at run level.
    """

    name: str
    """Artifact name (unique within the level)."""

    type: str
    """Type key from the artifact library (e.g. ``trace``, ``metrics``, ``plot``)."""

    path: Optional[str] = None
    """Path template.  If None, uses the default for the type."""

    validate: bool = False
    """Whether to validate the artifact schema after creation."""

    @property
    def effective_path(self) -> str:
        """Return the path template, falling back to the type default."""
        return self.path or _ARTIFACT_DEFAULT_PATHS.get(self.type, "{level_dir}/{name}")

    @property
    def format(self) -> str:
        """Return the file format for this artifact type."""
        info = _ARTIFACT_TYPE_REGISTRY.get(self.type, {})
        return info.get("format", "")

    @property
    def description(self) -> str:
        """Return the description for this artifact type."""
        info = _ARTIFACT_TYPE_REGISTRY.get(self.type, {})
        return info.get("description", "")

    @classmethod
    def from_entry(cls, name: str, value: Any) -> "ArtifactSpec":
        """Parse a single artifact entry from the YAML artifacts map.

        *value* is either a string (short form) or a dict (long form).
        """
        if isinstance(value, str):
            return cls(name=name, type=value)
        if isinstance(value, dict):
            return cls(
                name=name,
                type=value["type"],
                path=value.get("path"),
                validate=value.get("validate", False),
            )
        raise ValueError(f"Invalid artifact spec for '{name}': expected str or dict, got {type(value)}")


# ---------------------------------------------------------------------------
# LevelSpec — artifacts + pipeline at a hierarchy level
# ---------------------------------------------------------------------------

def _expand_pipeline_entries(
    entries: Any,
    *,
    level: str,
    phase: str,
    base_dir: Optional[Path] = None,
) -> List[PipelineStepSpec]:
    if not entries:
        return []
    if isinstance(entries, str):
        entries = [{"ref": entries}]
    if not isinstance(entries, list):
        raise ValueError(f"{level}.{phase} must be a list or pipeline file path")
    steps: List[PipelineStepSpec] = []
    for entry in entries:
        if isinstance(entry, dict) and "ref" in entry:
            ref_path = Path(entry["ref"])
            if not ref_path.is_absolute() and base_dir is not None:
                ref_path = (base_dir / ref_path).resolve()
            from mas.lab.benchmark.schedule.pipeline_resolve import (
                resolve_pipeline_specs_from_yaml,
            )

            for step in resolve_pipeline_specs_from_yaml(ref_path):
                if not step.scope:
                    step.scope = level
                if step.phase == "post" and phase == "pre":
                    step.phase = phase
                elif not step.phase:
                    step.phase = phase
                steps.append(step)
            continue
        if isinstance(entry, dict) and "steps" in entry:
            for step in entry["steps"]:
                steps.append(
                    PipelineStepSpec.from_dict({**step, "scope": level, "phase": phase})
                )
        elif isinstance(entry, dict) and "type" in entry:
            steps.append(
                PipelineStepSpec.from_dict({**entry, "scope": level, "phase": phase})
            )
        else:
            raise ValueError(
                f"{level}.{phase}: each entry must be a step object, "
                f"{{ref: path}}, {{steps: [...]}}, or a pipeline file path string"
            )
    return steps


@dataclass
class LevelSpec:
    """Artifacts and pipeline declared at one level of the experiment hierarchy.

    Levels (innermost → outermost):
        ``run`` → ``test`` → ``scenario`` → ``application``
    """

    level: str
    """Level name: ``run``, ``test``, ``scenario``, or ``application``."""

    artifacts: List[ArtifactSpec] = field(default_factory=list)
    """Artifacts declared at this level."""

    pipeline: List[PipelineStepSpec] = field(default_factory=list)
    """Pipeline steps executed at this level (from ``pre`` / ``post``)."""

    n_runs: Optional[int] = None
    """Run count (``run`` level only)."""

    @classmethod
    def from_dict(
        cls,
        level: str,
        data: Dict[str, Any],
        *,
        base_dir: Optional[Path] = None,
    ) -> "LevelSpec":
        if "pipeline" in data:
            raise ValueError(
                f"experiment.{level}.pipeline is removed; use {level}.pre or {level}.post"
            )
        artifacts = [
            ArtifactSpec.from_entry(name, value)
            for name, value in data.get("artifacts", {}).items()
        ]
        pipeline: List[PipelineStepSpec] = []
        pipeline.extend(
            _expand_pipeline_entries(
                data.get("pre", []), level=level, phase="pre", base_dir=base_dir
            )
        )
        pipeline.extend(
            _expand_pipeline_entries(
                data.get("post", []), level=level, phase="post", base_dir=base_dir
            )
        )
        for step in pipeline:
            if not step.scope:
                step.scope = level
        n_runs = data.get("n_runs") if level == "run" else None
        return cls(level=level, artifacts=artifacts, pipeline=pipeline, n_runs=n_runs)

