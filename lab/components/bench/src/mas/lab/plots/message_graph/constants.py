#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Layout constants for message-graph diagrams."""

# ---------------------------------------------------------------------------
# Layout constants  (px, matching the reference /tmp/agent-flow.svg)
# ---------------------------------------------------------------------------

_MARGIN_LEFT   = 130   # room for agent lane labels
_MARGIN_RIGHT  = 24    # right padding
_MARGIN_TOP    = 52    # room for title and iteration labels
_MARGIN_BOTTOM = 44    # room for tool squares below the bottom lane

_LANE_STEP = 44        # px between lane centres
_SLOT_W    = 46        # px per LLM-call x-slot (equal width)
_BOX_H     = 22        # px height of each LLM-call rectangle
_BOX_PAD   = 5         # px between box edge and slot edge on each side
_BOX_W     = _SLOT_W - 2 * _BOX_PAD   # = 36 px

_TOOL_TICK_H = 5       # px tick from box bottom to tool-square row
_TOOL_SIZE   = 8       # px side of each tool-call square
_TOOL_GAP    = 2       # px gap between consecutive tool squares

_LEGEND_SWATCH = 12    # px side of legend color swatch
_LEGEND_STEP   = 90    # px per legend item (swatch + gap + text + spacing)
_LEGEND_H      = 28    # px reserved at the bottom for the inline legend
_TIME_AXIS_H   = 28    # px reserved for the time axis row (when time_axis=True)
_BOX_W_MIN     = 20    # minimum box width in respect_timing mode

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

_AGENT_PALETTE = [
    "#CFA84B",  # golden
    "#A6C972",  # green
    "#DE895E",  # orange
    "#2CC3D4",  # cyan
    "#84C1F7",  # light blue
    "#9C95E9",  # purple
    "#D692D6",  # pink
    "#46B991",  # teal
    "#F06B6B",  # red
    "#FFB347",  # peach
]


