#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Shared colour palette for MAS trajectory plots.

Reuse these constants in any plot to ensure visual consistency.

Colour semantics
----------------
Levels (session → call): 3 shades of dark petrol blue (darkest at top,
lightest at agent level), then type-specific colours at the call level.

Usage::

    from mas.lab.plots.palette import PALETTE, level_color, call_type_color
"""

# ---------------------------------------------------------------------------
# Level colours — 3 shades of dark petrol blue
# ---------------------------------------------------------------------------
LEVEL_COLORS: dict[str, str] = {
    "session": "#0d3b4a",   # darkest petrol
    "mas":     "#155e75",   # dark petrol   (Tailwind cyan-900)
    "agent":   "#0e7490",   # petrol        (Tailwind cyan-700)
}

# ---------------------------------------------------------------------------
# Call-type colours
# ---------------------------------------------------------------------------
CALL_COLORS: dict[str, str] = {
    "llm":        "#ea580c",   # orange-600
    "tool":       "#16a34a",   # green-600
    "memory":     "#2563eb",   # blue-600
    "rag":        "#7c3aed",   # violet-600
    "processing": "#64748b",   # slate-500
    "default":    "#94a3b8",   # slate-400
}

# ---------------------------------------------------------------------------
# Full palette (merged for convenience)
# ---------------------------------------------------------------------------
PALETTE: dict[str, str] = {
    **LEVEL_COLORS,
    **CALL_COLORS,
    # Structural
    "bg":           "#f8fafc",   # slate-50
    "bg_dark":      "#0f172a",   # slate-900
    "lane_bg":      "#f1f5f9",   # slate-100
    "lane_bg_alt":  "#e2e8f0",   # slate-200
    "grid":         "#e2e8f0",   # slate-200
    "lifeline":     "#cbd5e1",   # slate-300
    "label":        "#334155",   # slate-700
    "title":        "#0f172a",   # slate-900
    "text_dark":    "#0f172a",
    "text_light":   "#f8fafc",
    "state_fill":   "#ffffff",
    "state_stroke": "#475569",   # slate-600
    "shared_conn":  "#94a3b8",   # slate-400
    "success":      "#16a34a",
    "failure":      "#dc2626",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def level_color(level: str) -> str:
    """Return the colour for a given span level name."""
    return PALETTE.get(level, PALETTE["default"])


def call_type_color(call_type: str) -> str:
    """Return the colour for a given call type (MASCall, LLMCall, …)."""
    _map: dict[str, str] = {
        "MASCall":         PALETTE["mas"],
        "AgentCall":       PALETTE["agent"],
        "LLMCall":         PALETTE["llm"],
        "ToolCall":        PALETTE["tool"],
        "MemoryCall":      PALETTE["memory"],
        "RAGQuery":        PALETTE["rag"],
        "ProcessingCall":  PALETTE["processing"],
    }
    return _map.get(call_type, PALETTE["default"])
