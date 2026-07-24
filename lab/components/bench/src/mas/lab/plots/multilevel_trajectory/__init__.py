#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Multilevel trajectory plot.

Pipeline
--------
::

    events (list[dict])
        │
        ▼  _build_call_records
    records (list[dict])        ← typed execution records, paired start/end, call_id assigned
        │
        ▼  _build_call_tree
    children_of, parent_of      ← immediate parent–child by timestamp containment
        │
        ├─▶  _make_agent_sequence   ← DFS on agent subtree → flat ordered fragments
        └─▶  _make_call_sequence    ← direct call children of each agent fragment
        │
        ▼  _build_dag
    (state_reg, lanes)          ← StateNode registry + LaneDef sequences
        │
         ┌──────────┴──────────┐
         ▼                     ▼
      _render_svg         _build_chart_data + assets/multilevel.html

Public entry point: ``plot_multilevel_trajectory(trace, fmt, ...)``
"""

from mas.lab.plots.multilevel_trajectory.annotations import (
    _collect_annotations,
    _collect_context_provenance,
    _derive_context_semantics,
    _format_cpr_hover,
    _source_category,
    _stagger_coinc_processing_calls,
)
from mas.lab.plots.multilevel_trajectory.chart_data import (
    _build_chart_data,
    _fmt_d3_html,
    build_trajectory_chart_data,
    build_trajectory_chart_data_from_kg,
)
from mas.lab.plots.multilevel_trajectory.constants import (
    TYPE_COLOR,
    TYPE_LABEL,
    _CALL_TYPE_TO_LEVEL,
    _INSTANT_ICON,
    _INSTANT_ICON_DEFAULT,
    _KIND_BASE_TO_TYPE,
    _PROC_TYPE_LABEL,
    _TS_TOL,
)
from mas.lab.plots.multilevel_trajectory.dag import _build_dag
from mas.lab.plots.multilevel_trajectory.layout import (
    _WIDTH_MODES,
    _compute_x_positions,
)
from mas.lab.plots.multilevel_trajectory.models import LaneDef, StateNode, TransNode
from mas.lab.plots.multilevel_trajectory.plot import (
    plot_multilevel_trajectory,
    plot_multilevel_trajectory_from_kg,
)
from mas.lab.plots.multilevel_trajectory.records import (
    _build_call_label,
    _build_call_records,
    _extract_final_output,
    _extract_user_input,
    _synthesize_thinking_records,
)
from mas.lab.plots.multilevel_trajectory.svg import (
    _ARR_GAP,
    _BADGE_F,
    _BADGE_R,
    _BG,
    _CONN_C,
    _LABEL_C,
    _LABEL_W,
    _LANE_ALT,
    _LANE_BG,
    _LANE_H,
    _LANE_MID,
    _LEGEND_H,
    _MIN_TRANS_W,
    _PAD_BOT,
    _PAD_L,
    _PAD_R,
    _SEP,
    _STATE_F,
    _STATE_H,
    _STATE_S,
    _STATE_T,
    _STATE_W,
    _TITLE_C,
    _TITLE_H,
    _TRANS_H,
    _USER_ACTOR_C,
    _USER_ACTOR_OFFSET,
    _ea,
    _esc,
    _render_svg,
)
from mas.lab.plots.multilevel_trajectory.tree import (
    _align_record_boundaries,
    _build_call_tree,
    _make_agent_sequence,
    _make_call_sequence,
)
from mas.lab.plots.trajectory import load_trace

__all__ = [
    "load_trace",
    "plot_multilevel_trajectory",
    "plot_multilevel_trajectory_from_kg",
    "build_trajectory_chart_data",
    "build_trajectory_chart_data_from_kg",
]
