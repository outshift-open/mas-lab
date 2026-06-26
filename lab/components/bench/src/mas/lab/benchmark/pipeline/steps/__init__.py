#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OSS pipeline step library — one step class per module, grouped by category.

Categories: ``extract/``, ``eval/``, ``viz/``, ``data/``, ``services/``.
Shared helpers live in ``mas.lab.benchmark.pipeline.lib``.

Internal-only steps (``embed_states``, ``list_clickhouse_sessions``, …) ship in
``mas-lab-internal/lab-components/bench-steps`` and register via the
``mas.lab.pipeline_steps`` entry-point group when that package is installed.
"""

from mas.lab.benchmark.pipeline.steps.data.analysis import AnalysisStep
from mas.lab.benchmark.pipeline.steps.data.collect_dataframe import CollectDataFrameStep
from mas.lab.benchmark.pipeline.steps.data.dataset import DatasetStep
from mas.lab.benchmark.pipeline.steps.data.deserialize import DeserializeStep
from mas.lab.benchmark.pipeline.steps.data.diff_trajectories import DiffTrajectoriesStep
from mas.lab.benchmark.pipeline.steps.data.embed_trajectories import EmbedStep
from mas.lab.benchmark.pipeline.steps.data.experiment import ExperimentStep
from mas.lab.benchmark.pipeline.steps.data.gather_level import GatherLevelStep
from mas.lab.benchmark.pipeline.steps.data.generate_dataset import GenerateDatasetStep
from mas.lab.benchmark.pipeline.steps.data.join_dataframe import JoinDataFrameStep
from mas.lab.benchmark.pipeline.steps.data.processor import ProcessorStep
from mas.lab.benchmark.pipeline.steps.data.serialize import SerializeStep
from mas.lab.benchmark.pipeline.steps.data.to_dataframe import ToDataFrameStep
from mas.lab.benchmark.pipeline.steps.data.to_impact_dataframe import ToImpactDataFrameStep
from mas.lab.benchmark.pipeline.steps.eval.annotate_metrics import AnnotateMetricsStep
from mas.lab.benchmark.pipeline.steps.eval.batch import EvalBatchStep
from mas.lab.benchmark.pipeline.steps.eval.adversarial import EvalAdversarialStep
from mas.lab.benchmark.pipeline.steps.eval.collect_metrics import CollectMetricsStep
from mas.lab.benchmark.pipeline.steps.eval.compute_ci import ComputeCIStep
from mas.lab.benchmark.pipeline.steps.eval.compute_drift import ComputeDriftStep
from mas.lab.benchmark.pipeline.steps.eval.mce import EvalMceStep
from mas.lab.benchmark.pipeline.steps.eval.trip_planner_gt import EvalTripPlannerGTStep
from mas.lab.benchmark.pipeline.steps.extract.mealy_stats import ExtractMealyStatsStep
from mas.lab.benchmark.pipeline.steps.extract.sys_stats import ExtractSysStatsStep
from mas.lab.benchmark.pipeline.steps.extract.trace_stats import ExtractTraceStatsStep
from mas.lab.benchmark.pipeline.steps.extract.trajectories import ExtractTrajectoriesStep
from mas.lab.benchmark.pipeline.steps.services.export_otel import ExportOtelStep
from mas.lab.benchmark.pipeline.steps.services.service_start import ServiceStartStep
from mas.lab.benchmark.pipeline.steps.services.service_stop import ServiceStopStep
from mas.lab.benchmark.pipeline.steps.viz.ci_plot import CIPlotStep
from mas.lab.benchmark.pipeline.steps.viz.metrics_comparison_plot import MetricsComparisonPlotStep
from mas.lab.benchmark.pipeline.steps.viz.pipeline_diagram import PipelineDiagramStep
from mas.lab.benchmark.pipeline.steps.viz.plot import PlotStep
from mas.lab.benchmark.pipeline.steps.viz.plot_communication_flow import PlotCommunicationFlowStep
from mas.lab.benchmark.pipeline.steps.viz.plot_ggplot import PlotPipelineStep
from mas.lab.benchmark.pipeline.steps.viz.plot_message_graph import PlotMessageGraphStep
from mas.lab.benchmark.pipeline.steps.viz.plot_multilevel_trajectory import PlotMultilevelTrajectoryStep
from mas.lab.benchmark.pipeline.steps.viz.plot_multilevel_trajectory_batch import (
    PlotMultilevelTrajectoryBatchStep,
)
from mas.lab.benchmark.pipeline.steps.viz.plot_trajectory import PlotTrajectoryStep
from mas.lab.benchmark.pipeline.steps.viz.plot_trajectory_batch import PlotTrajectoryBatchStep
from mas.lab.benchmark.pipeline.steps.viz.plotnine import PlotNineStep

__all__ = [
    "AnalysisStep",
    "AnnotateMetricsStep",
    "CIPlotStep",
    "CollectDataFrameStep",
    "CollectMetricsStep",
    "ComputeCIStep",
    "ComputeDriftStep",
    "DatasetStep",
    "DeserializeStep",
    "DiffTrajectoriesStep",
    "EmbedStep",
    "EvalAdversarialStep",
    "EvalBatchStep",
    "EvalMceStep",
    "EvalTripPlannerGTStep",
    "ExperimentStep",
    "ExportOtelStep",
    "ExtractMealyStatsStep",
    "ExtractSysStatsStep",
    "ExtractTraceStatsStep",
    "ExtractTrajectoriesStep",
    "GatherLevelStep",
    "GenerateDatasetStep",
    "JoinDataFrameStep",
    "MetricsComparisonPlotStep",
    "PipelineDiagramStep",
    "PlotCommunicationFlowStep",
    "PlotMessageGraphStep",
    "PlotMultilevelTrajectoryBatchStep",
    "PlotMultilevelTrajectoryStep",
    "PlotNineStep",
    "PlotPipelineStep",
    "PlotStep",
    "PlotTrajectoryBatchStep",
    "PlotTrajectoryStep",
    "ProcessorStep",
    "SerializeStep",
    "ServiceStartStep",
    "ServiceStopStep",
    "ToDataFrameStep",
    "ToImpactDataFrameStep",
]
