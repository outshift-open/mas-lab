#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Message-graph plot — whole-run agent message-flow diagram."""

from mas.lab.plots.message_graph.constants import (
    _AGENT_PALETTE,
    _BOX_H,
    _BOX_PAD,
    _BOX_W,
    _BOX_W_MIN,
    _LANE_STEP,
    _LEGEND_H,
    _LEGEND_STEP,
    _LEGEND_SWATCH,
    _MARGIN_BOTTOM,
    _MARGIN_LEFT,
    _MARGIN_RIGHT,
    _MARGIN_TOP,
    _SLOT_W,
    _TIME_AXIS_H,
    _TOOL_GAP,
    _TOOL_SIZE,
    _TOOL_TICK_H,
)
from mas.lab.plots.message_graph.extract import (
    _assign_iterations,
    _extract,
    _find_root_agent_id,
)
from mas.lab.plots.message_graph.helpers import (
    _agent_color,
    _dur_str,
    _preview,
    _tip_attrs,
)
from mas.lab.plots.message_graph.layout import (
    _box_left,
    _box_right,
    _box_top,
    _lane_y,
    _slot_cx,
)
from mas.lab.plots.message_graph.plot import plot_message_graph
from mas.lab.plots.message_graph.processor import MessageGraphPlotter
from mas.lab.plots.message_graph.theme import (
    _DARK,
    _HTML_WRAPPER,
    _LIGHT,
    _SVG_CLASS_STYLES,
    _build_svg_css,
    _vars_block,
)

__all__ = [
    "MessageGraphPlotter",
    "plot_message_graph",
]
