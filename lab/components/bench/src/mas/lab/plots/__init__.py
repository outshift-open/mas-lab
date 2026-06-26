#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.lab.plots — trajectory and MAS visualisation helpers.

Public API::

    from mas.lab.plots.trajectory import load_trace, plot_trajectory
    from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory
    from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory_from_kg
    from mas.lab.plots.multilevel_trajectory import build_trajectory_chart_data
    from mas.lab.plots.multilevel_trajectory import build_trajectory_chart_data_from_kg
    from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory
    from mas.lab.plots.multilevel_trajectory_processor import MultilevelTrajectoryPlotter
    from mas.lab.plots.communication_flow import plot_communication_flow
    from mas.lab.plots.communication_flow import CommunicationFlowPlotter
    from mas.lab.plots.palette import PALETTE, level_color, call_type_color
    from mas.lab.plots.pipeline_diagram import plot_pipeline
    from mas.lab.plots.kg_adapter import FacetQuery, KGSource, KGView

``plot_multilevel_trajectory`` — canonical trajectory plot (parallel agents, governance, memory, KG-free).
``build_trajectory_chart_data_from_kg`` — KG-backed data-prep stage (for live WS path).
``plot_pipeline`` — pipeline DAG diagram (SVG static / HTML interactive).
``FacetQuery`` — filter spec for KG-backed trajectory queries (JSON-serialisable).
``KGSource`` — data source: KG + FacetQuery → (records, events).
``KGView`` — low-level faceted access layer (``query(call_type, **kw)``).
"""
from mas.lab.plots.trajectory import load_trace, plot_trajectory
from mas.lab.plots.multilevel_trajectory import (
    plot_multilevel_trajectory,
    plot_multilevel_trajectory_from_kg,
    build_trajectory_chart_data,
    build_trajectory_chart_data_from_kg,
)
from mas.lab.plots.multilevel_trajectory_processor import MultilevelTrajectoryPlotter
from mas.lab.plots.communication_flow import plot_communication_flow, CommunicationFlowPlotter
from mas.lab.plots.palette import PALETTE, level_color, call_type_color
from mas.lab.plots.loaders import TrajectoryLoader  # noqa: F401 — registers trajectory-loader
from mas.lab.plots.message_graph import plot_message_graph
from mas.lab.plots.multilevel_context_provenance import plot_multilevel_context_provenance
from mas.lab.plots.pipeline_diagram import plot_pipeline
from mas.lab.plots.kg_adapter import FacetQuery, KGSource, KGView
from mas.lab.plots.mas_plot import (   # noqa: F401
    MASPlot,
    theme_mas, theme_mas_paper, theme_mas_slides, theme_mas_web,
    scale_fill_oi, scale_color_oi, scale_linetype_mas,
    OI, OI_COLORS, C_SA, C_MAS, C_OK, C_TRIG, C_NA,
    PAPER_COL1, PAPER_COL2, sem,
)

__all__ = [
    "load_trace",
    "plot_trajectory",
    "plot_multilevel_trajectory",
    "MultilevelTrajectoryPlotter",
    "plot_communication_flow",
    "CommunicationFlowPlotter",
    "TrajectoryLoader",
    "plot_message_graph",
    "plot_multilevel_context_provenance",
    "plot_pipeline",
    "MASPlot",
    "theme_mas", "theme_mas_paper", "theme_mas_slides", "theme_mas_web",
    "scale_fill_oi", "scale_color_oi", "scale_linetype_mas",
    "OI", "OI_COLORS", "C_SA", "C_MAS", "C_OK", "C_TRIG", "C_NA",
    "PAPER_COL1", "PAPER_COL2", "sem",
    "PALETTE",
    "level_color",
    "call_type_color",
]
