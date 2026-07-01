#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.lab.benchmark.experiment import EvaluationSpec
from mas.runtime.spec.source import resolve_path as resolve_path_ref

from .lab_context import _discover_lab_name
from .pipeline import ArtifactSpec, LevelSpec, PipelineStepSpec
from .scenario import MASScenarioSpec, MASSpec
from .scenario_loading import discover_scenario_stems

_DEPRECATED_EXPERIMENT_KEYS = {
    "mas": "use applications: [{app|manifest, configs_dir}]",
    "pipeline": "use application: { post: [...] }",
    "output_dir": "remove; output paths are derived from lab layout",
    "flavours": "use default_flavour (library-standard flavours)",
    "plots": "declare plot steps in application.post / scenario.post pipelines",
}


def _reject_deprecated_experiment_keys(data: Dict[str, Any], *, path: Optional[Path]) -> None:
    label = str(path) if path else "experiment"
    for key, hint in _DEPRECATED_EXPERIMENT_KEYS.items():
        if key in data:
            raise ValueError(f"{label}: removed key {key!r}; {hint}")


@dataclass
class MASRunBase:
    """Shared base for all MAS run configs (lab and experiment).

    Relationship to single-agent ExperimentConfig
    ---------------------------------------------
    * ``scenarios``  ↔  variants (named execution contexts)
    * ``dataset``    ↔  dataset path (same JSON format)
    * ``evaluation`` ↔  EvaluationSpec (shared class, zero duplication)
    * ``output_dir`` ↔  output_dir (aligned with BenchmarkRunManager)
    * ``mas``        — replaces ``agent`` (multi-agent pointer instead of single manifest)
    """

    name: str
    description: str = ""

    lab_name: Optional[str] = None
    """Lab this experiment belongs to.

    Auto-discovered from a sibling ``lab-config.yaml`` file (``lab.name`` field)
    or from the ``.lab`` directory naming convention.  When set, the
    output-directory hierarchy becomes::

        <labs_root>/<lab_name>/<experiment_name>/

    instead of the flat ``benchmark_root()/<experiment_name>`` path.
    """

    mas: Optional[MASSpec] = None
    """MAS configuration pointer (required for any run)."""

    scenarios: List[MASScenarioSpec] = field(default_factory=list)
    """Ordered list of scenario specs.

    If empty, scenarios are auto-discovered from ``mas.effective_configs_dir/*.yaml``.
    """

    dataset: Optional[Path] = None
    """Optional path to a prompts dataset JSON (same format as ExperimentConfig)."""

    dataset_filter: Dict[str, Any] = field(default_factory=dict)
    """Metadata filters applied after loading the dataset (e.g. ``group: single_agent``)."""

    dataset_limit: Optional[int] = None
    """Maximum number of dataset items to use (applied after filtering)."""

    evaluation: Optional[EvaluationSpec] = None
    """Evaluation spec — reused verbatim from ExperimentConfig conventions."""

    output_dir: Path = field(default_factory=lambda: Path("./output"))
    """Where per-run outputs are written (JSONL feeds, artefacts, metrics)."""

    trace_cache_dir: Optional[Path] = None
    """Override the global trace-cache directory for this experiment.

    Priority chain (highest first):
    1. CLI ``--trace-cache`` flag
    2. This YAML field (``trace_cache_dir:``)
    3. Env var ``MAS_TRACE_CACHE``
    4. Default ``$XDG_CACHE_HOME/mas/traces``
    """

    pipeline: List["PipelineStepSpec"] = field(default_factory=list)
    """Inline pipeline steps declared in the experiment manifest."""

    pipeline_ref: Optional[str] = None
    """External pipeline YAML path (relative to experiment dir). Resolved at schedule time."""

    pipeline_app: Optional[Dict[str, Any]] = None
    """App bundle pipeline pointer: ``{app: name, name: pipeline.yaml}``."""

    levels: Dict[str, "LevelSpec"] = field(default_factory=dict)
    """(v2) Level sections: ``run``, ``test``, ``scenario``.

    Each level declares its own artifacts and pipeline.  The experiment-level
    pipeline and artifacts live directly in ``pipeline`` / ``artifacts`` fields
    on the parent config (not in a separate level).
    """

    artifacts: List["ArtifactSpec"] = field(default_factory=list)
    """(v2) Experiment-level artifact declarations.

    Short form: ``metrics: metrics``.
    Long form: ``trajectory: {type: plot, path: "..."}``.
    """

    pipeline_resources: List[Dict[str, Any]] = field(default_factory=list)
    """Scoped resource declarations for the pipeline.

    Resources are instantiated at their declared scope and shared with steps
    that reference them via ``@resource:<name>`` in their config.

    Example::

        pipeline_resources:
          - name: shared-metrics
            type: metrics
            scope: test      # persists across runs within a test
    """

    # Keep a reference to the source file for relative-path resolution.
    _path: Optional[Path] = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Shared accessors
    # ------------------------------------------------------------------

    @property
    def is_v2(self) -> bool:
        """Detect v2 level-based format (any of run:/test:/scenario:/experiment: present)."""
        return bool(self.levels)

    def all_artifacts(self) -> Dict[str, "ArtifactSpec"]:
        """Return all artifacts across all levels + experiment, keyed by name."""
        result: Dict[str, ArtifactSpec] = {}
        for level_spec in self.levels.values():
            for art in level_spec.artifacts:
                result[art.name] = art
        for art in self.artifacts:
            result[art.name] = art
        return result

    def all_pipeline_steps(self) -> List["PipelineStepSpec"]:
        """Return all pipeline steps from all levels + experiment.

        Steps from inner levels come first (run, test, scenario) then
        experiment-level.  Each step has its ``scope`` set.

        Both level ``pre``/``post`` hooks and the flat ``pipeline`` field on
        :class:`MASRunBase` are combined (level hooks first).
        """
        steps: List[PipelineStepSpec] = []
        for level_name in ("run", "test", "scenario", "application"):
            if level_name in self.levels:
                steps.extend(self.levels[level_name].pipeline)
        steps.extend(self.pipeline)
        return steps

    def scenario_ids(self) -> List[str]:
        """Return the ordered list of scenario IDs.

        Uses the declared ``scenarios`` list when present (preserves order and
        allows custom descriptions).  Falls back to alphabetical discovery
        from ``mas.effective_configs_dir`` when the list is empty.
        """
        if self.scenarios:
            return [s.id for s in self.scenarios]
        if self.mas:
            cd = self.mas.effective_configs_dir
            if cd and cd.exists():
                return discover_scenario_stems(cd)
        return []

    def get_scenario(self, scenario_id: str) -> Optional[MASScenarioSpec]:
        """Look up a declared scenario by ID (returns None if not found)."""
        for s in self.scenarios:
            if s.id == scenario_id:
                return s
        return None

    def configs_dir(self) -> Optional[Path]:
        """Return the MAS configs directory (convenience accessor)."""
        return self.mas.effective_configs_dir if self.mas else None

    # ------------------------------------------------------------------
    # Internal YAML loader helper
    # ------------------------------------------------------------------

    @classmethod
    def _load_base_fields(
        cls,
        data: Dict[str, Any],
        base_dir: Path,
        yaml_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Parse the shared fields from a raw YAML dict.

        *yaml_path* is the source file path — used for lab-context discovery
        (``lab-config.yaml`` neighbour or ``.lab`` parent-directory convention).
        Pass it whenever the path is known.

        Returns a kwargs dict that subclass ``from_yaml`` methods can spread
        into their constructors.
        """
        from mas.lab import paths as _paths

        _reject_deprecated_experiment_keys(data, path=yaml_path)

        mas: Optional[MASSpec] = None
        if "applications" in data:
            # applications: [{app: trip-planner}]  →  mas: {app: trip-planner}
            apps_list = data["applications"]
            if isinstance(apps_list, list) and apps_list:
                mas = MASSpec.from_dict(apps_list[0], base_dir)

        scenarios = [
            MASScenarioSpec.from_dict(s, base_dir)
            for s in data.get("scenarios", [])
        ]

        dataset: Optional[Path] = None
        dataset_filter: Dict[str, Any] = {}
        dataset_limit: Optional[int] = None
        if "dataset" in data:
            ds = data["dataset"]
            if "app" in ds:
                # app: trip-planner  →  apps/trip-planner/datasets/<name>.yaml (legacy)
                # Prefer registry: dataset.name: trip-planner-benchmark
                from mas.apps import get_app
                _dataset_name = ds.get("name", "benchmark")
                dataset = (get_app(ds["app"]) / "datasets" / f"{_dataset_name}.yaml").resolve()
            elif "name" in ds:
                locator = ds.get("locator")
                if locator:
                    from mas.lab.benchmark.experiment import _resolve_dataset_by_name

                    dataset = _resolve_dataset_by_name(
                        base_dir, str(ds["name"]), locator=str(locator)
                    )
                else:
                    from mas.lab.benchmark.experiment import _resolve_dataset_by_name

                    try:
                        dataset = _resolve_dataset_by_name(
                            base_dir, str(ds["name"]), locator=None
                        )
                    except FileNotFoundError:
                        dataset = resolve_path_ref(
                            f"datasets/{ds['name']}.yaml", base_dir
                        )
            else:
                dataset = resolve_path_ref(ds["path"], base_dir)
            # Filtering: group shorthand or explicit filter dict
            if "group" in ds:
                dataset_filter["group"] = ds["group"]
            if "filter" in ds:
                dataset_filter.update(ds["filter"])
            if "limit" in ds:
                dataset_limit = int(ds["limit"])

        evaluation: Optional[EvaluationSpec] = None
        if "evaluation" in data:
            evaluation = EvaluationSpec.from_dict(data["evaluation"])

        # Output directory is always auto-derived from lab context.
        exp_name = data.get("name", "unnamed")
        lab_name: Optional[str] = None
        if yaml_path is not None:
            lab_name = _discover_lab_name(yaml_path)
        if lab_name:
            output_dir = _paths.labs_root() / lab_name / exp_name
        else:
            output_dir = _paths.benchmark_root() / exp_name

        trace_cache_dir: Optional[Path] = None
        if "trace_cache_dir" in data:
            trace_cache_dir = (base_dir / data["trace_cache_dir"]).resolve()

        pipeline: List["PipelineStepSpec"] = []
        pipeline_ref: Optional[str] = None
        pipeline_app: Optional[Dict[str, Any]] = None

        pipeline_resources: List[Dict[str, Any]] = data.get("pipeline_resources", [])

        levels: Dict[str, LevelSpec] = {}
        for level_name in ("run", "test", "scenario", "application"):
            if level_name in data:
                levels[level_name] = LevelSpec.from_dict(level_name, data[level_name])

        # v2 experiment-level artifacts
        artifacts: List[ArtifactSpec] = [
            ArtifactSpec.from_entry(name, value)
            for name, value in data.get("artifacts", {}).items()
        ]

        # Stamp application-level steps when loaded from application.post.
        if "application" in levels:
            for step in levels["application"].pipeline:
                if not step.scope:
                    step.scope = "application"

        return dict(
            name=exp_name,
            description=data.get("description", ""),
            lab_name=lab_name,
            mas=mas,
            scenarios=scenarios,
            dataset=dataset,
            dataset_filter=dataset_filter,
            dataset_limit=dataset_limit,
            evaluation=evaluation,
            output_dir=output_dir,
            trace_cache_dir=trace_cache_dir,
            pipeline=pipeline,
            pipeline_ref=pipeline_ref,
            pipeline_app=pipeline_app,
            pipeline_resources=pipeline_resources,
            levels=levels,
            artifacts=artifacts,
        )

