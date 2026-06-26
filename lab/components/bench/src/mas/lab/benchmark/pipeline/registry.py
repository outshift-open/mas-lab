#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pipeline step type registry and dynamic class resolution."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_CUSTOM_STEP_TYPES: Dict[str, type] = {}


def register_step_type(step_type: str, step_class: type) -> None:
    """Register a custom pipeline step type."""
    _CUSTOM_STEP_TYPES[step_type] = step_class


def _entry_point_steps() -> Dict[str, type]:
    """Load optional steps from ``mas.lab.pipeline_steps`` entry points (internal extensions)."""
    registry: Dict[str, type] = {}
    try:
        eps = importlib.metadata.entry_points(group="mas.lab.pipeline_steps")
    except Exception as exc:
        logger.debug("mas.lab.pipeline_steps entry points unavailable: %s", exc)
        return registry
    for ep in eps:
        try:
            cls = ep.load()
            registry[ep.name] = cls
        except Exception as exc:
            logger.warning("Failed to load pipeline step entry point %r: %s", ep.name, exc)
    return registry


def _builtin_step_registry() -> Dict[str, type]:
    """Return the built-in OSS step class registry (lazy-loaded)."""
    from mas.lab.benchmark.pipeline.steps import (
        AnalysisStep,
        AnnotateMetricsStep,
        CIPlotStep,
        CollectDataFrameStep,
        CollectMetricsStep,
        ComputeCIStep,
        ComputeDriftStep,
        DatasetStep,
        DeserializeStep,
        DiffTrajectoriesStep,
        EmbedStep,
        EvalAdversarialStep,
        EvalBatchStep,
        EvalMceStep,
        EvalTripPlannerGTStep,
        ExperimentStep,
        ExportOtelStep,
        ExtractMealyStatsStep,
        ExtractSysStatsStep,
        ExtractTraceStatsStep,
        ExtractTrajectoriesStep,
        GatherLevelStep,
        GenerateDatasetStep,
        JoinDataFrameStep,
        MetricsComparisonPlotStep,
        PipelineDiagramStep,
        PlotCommunicationFlowStep,
        PlotMessageGraphStep,
        PlotMultilevelTrajectoryBatchStep,
        PlotMultilevelTrajectoryStep,
        PlotNineStep,
        PlotPipelineStep,
        PlotStep,
        PlotTrajectoryBatchStep,
        PlotTrajectoryStep,
        ProcessorStep,
        SerializeStep,
        ServiceStartStep,
        ServiceStopStep,
        ToDataFrameStep,
        ToImpactDataFrameStep,
    )

    registry: Dict[str, type] = {
        "dataset": DatasetStep,
        "experiment": ExperimentStep,
        "analysis": AnalysisStep,
        "plot": PlotStep,
        "plot_trajectory": PlotTrajectoryStep,
        "plot_trajectory_batch": PlotTrajectoryBatchStep,
        "extract_trajectories": ExtractTrajectoriesStep,
        "annotate_metrics": AnnotateMetricsStep,
        "eval_mce": EvalMceStep,
        "generate_dataset": GenerateDatasetStep,
        "embed_trajectories": EmbedStep,
        "compute_drift": ComputeDriftStep,
        "to_impact_dataframe": ToImpactDataFrameStep,
        "processor": ProcessorStep,
        "metrics_comparison_plot": MetricsComparisonPlotStep,
        "collect_metrics": CollectMetricsStep,
        "collect_dataframe": CollectDataFrameStep,
        "gather_level": GatherLevelStep,
        "plotnine": PlotNineStep,
        "ggplot": PlotPipelineStep,
        "ci_plot": CIPlotStep,
        "compute_ci": ComputeCIStep,
        "diff_trajectories": DiffTrajectoriesStep,
        "eval_adversarial": EvalAdversarialStep,
        "eval_trip_planner_gt": EvalTripPlannerGTStep,
        "to_dataframe": ToDataFrameStep,
        "join_dataframe": JoinDataFrameStep,
        "pipeline_diagram": PipelineDiagramStep,
        "extract_trace_stats": ExtractTraceStatsStep,
        "extract_mealy_stats": ExtractMealyStatsStep,
        "extract_sys_stats": ExtractSysStatsStep,
        "service_start": ServiceStartStep,
        "service_stop": ServiceStopStep,
        "serialize": SerializeStep,
        "deserialize": DeserializeStep,
        "plot_multilevel_trajectory": PlotMultilevelTrajectoryStep,
        "plot_multilevel_trajectory_batch": PlotMultilevelTrajectoryBatchStep,
        "plot_communication_flow": PlotCommunicationFlowStep,
        "plot_message_graph": PlotMessageGraphStep,
        "export_otel": ExportOtelStep,
    }

    registry.update(_entry_point_steps())
    return registry


def get_step_registry() -> Dict[str, type]:
    """Return a dict mapping step-type strings to their PipelineStep subclasses."""
    return _builtin_step_registry()


def _import_class(spec: str, base_dir: Optional[Path] = None) -> type:
    if ".py:" in spec:
        file_part, class_name = spec.rsplit(":", 1)
        file_path = Path(file_part)
        if not file_path.is_absolute():
            root = base_dir or Path.cwd()
            file_path = root / file_path
        file_path = file_path.resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Step file not found: {file_path}")
        module_name = f"_user_steps.{file_path.stem}"
        spec_obj = importlib.util.spec_from_file_location(module_name, file_path)
        if spec_obj is None or spec_obj.loader is None:
            raise ImportError(f"Cannot load module from {file_path}")
        module = importlib.util.module_from_spec(spec_obj)
        sys.modules[module_name] = module
        spec_obj.loader.exec_module(module)
        return getattr(module, class_name)

    if ":" in spec:
        module_path, class_name = spec.rsplit(":", 1)
    elif "." in spec:
        module_path, class_name = spec.rsplit(".", 1)
    else:
        raise ValueError(
            f"Cannot resolve step type {spec!r}. "
            f"Use a built-in name, 'module.path:ClassName', or './file.py:ClassName'."
        )

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _resolve_step_class(step_type: str, base_dir: Optional[Path] = None) -> type:
    from mas.lab.benchmark.pipeline.core import PipelineStep

    registry = _builtin_step_registry()
    step_class = registry.get(step_type)
    if step_class is not None:
        return step_class

    custom = _CUSTOM_STEP_TYPES.get(step_type)
    if custom is not None:
        return custom

    try:
        cls = _import_class(step_type, base_dir=base_dir)
    except Exception as exc:
        known = ", ".join(sorted(registry.keys()))
        raise ValueError(
            f"Unknown step type: {step_type!r}. "
            f"Built-in types: {known}. "
            f"For custom steps, use 'module.path:ClassName' or './file.py:ClassName'. "
            f"Import error: {exc}"
        ) from exc

    if not (isinstance(cls, type) and issubclass(cls, PipelineStep)):
        raise TypeError(
            f"Step type {step_type!r} resolved to {cls!r}, "
            f"which is not a PipelineStep subclass."
        )
    return cls


__all__ = [
    "_CUSTOM_STEP_TYPES",
    "register_step_type",
    "get_step_registry",
    "_import_class",
    "_resolve_step_class",
    "_builtin_step_registry",
]
