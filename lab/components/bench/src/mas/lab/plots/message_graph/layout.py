#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""SVG geometry helpers."""

# ---------------------------------------------------------------------------
# SVG geometry helpers
# ---------------------------------------------------------------------------

def _lane_y(agent_idx_map: dict[str, int], agent_id: str) -> float:
    return _MARGIN_TOP + (agent_idx_map.get(agent_id, 0) + 0.5) * _LANE_STEP


def _slot_cx(slot_index: int) -> float:
    return _MARGIN_LEFT + (slot_index + 0.5) * _SLOT_W


def _box_left(slot_index: int) -> float:
    return _slot_cx(slot_index) - _BOX_W / 2


def _box_right(slot_index: int) -> float:
    return _slot_cx(slot_index) + _BOX_W / 2


def _box_top(agent_idx_map: dict[str, int], agent_id: str) -> float:
    return _lane_y(agent_idx_map, agent_id) - _BOX_H / 2


def _fmt_time_s(t: float) -> str:
    """Format elapsed seconds as a compact human-readable string."""
    if t < 60:
        return f"{t:.0f}s"
    m = int(t // 60)
    s = int(t % 60)
    return f"{m}m{s:02d}s" if s else f"{m}m"


def _nice_time_interval(span: float, max_ticks: int = 10) -> float:
    """Return a human-readable tick interval for a time span (seconds)."""
    candidates = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600]
    raw = span / max(max_ticks, 1)
    for c in candidates:
        if c >= raw:
            return c
    return candidates[-1]

