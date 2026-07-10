#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Column layout: timestamp buckets → pixel x-positions."""

import math

_WIDTH_MODES = ("fixed", "proportional", "log")


def _compute_x_positions(
    buckets_sorted: list[float],
    label_w: float,
    pad_l: float,
    min_col: float = 150.0,
    width_mode: str = "fixed",
    instant_pairs: frozenset[tuple[float, float]] = frozenset(),
) -> dict[float, float]:
    """Assign a centre-x pixel coordinate to every bucket timestamp.

    width_mode
    ----------
    ``"fixed"``         Equal column width regardless of duration (default).
    ``"proportional"``  Column width proportional to wall-clock duration.
    ``"log"``           Log-scaled duration — compresses very long calls
                        while keeping short ones readable.
    """
    if not buckets_sorted:
        return {}
    if len(buckets_sorted) == 1:
        return {buckets_sorted[0]: label_w + pad_l}

    n  = len(buckets_sorted)
    t0 = buckets_sorted[0]

    if width_mode == "fixed":
        raw_steps = [1.0] * (n - 1)
    elif width_mode == "proportional":
        raw_steps = [
            max(1e-9, buckets_sorted[i] - buckets_sorted[i - 1])
            for i in range(1, n)
        ]
    elif width_mode == "log":
        raw_steps = [
            math.log1p(max(0.0, buckets_sorted[i] - buckets_sorted[i - 1])) ** 0.5
            for i in range(1, n)
        ]
    else:
        raise ValueError(f"width_mode must be one of {_WIDTH_MODES}, got '{width_mode}'")

    # Classify each interval: only genuine instant-call columns (ToolCall,
    # MemoryCall, RAGQuery with is_instant=True) get a fixed narrow width.
    # Do NOT rely on timestamp proximity — a LLMCall that starts a few ms after
    # the previous state would be misclassified as instant by a TS_TOL check.
    _INSTANT_COL_W = 130.0  # px — SW/2 + 48px arrow + SW(icon) + 48px arrow + SW/2
    is_inst = [
        (buckets_sorted[i], buckets_sorted[i + 1]) in instant_pairs
        for i in range(n - 1)
    ]
    n_instant = sum(is_inst)
    n_normal  = (n - 1) - n_instant

    # Total canvas for normal columns: proportional to the column count so
    # sparse traces aren't stretched across a fixed 1400px floor (which left
    # very wide gaps between a handful of calls). Each normal column ≈160px.
    normal_total = n_normal * 160.0 if n_normal else 0.0
    normal_raw_steps = [r for r, inst in zip(raw_steps, is_inst) if not inst]
    normal_raw_total = sum(normal_raw_steps) or 1.0

    x = label_w + pad_l
    positions: dict[float, float] = {t0: x}
    for i, raw in enumerate(raw_steps):
        if is_inst[i]:
            step = _INSTANT_COL_W
        else:
            step = max(min_col, raw / normal_raw_total * normal_total)
        x += step
        positions[buckets_sorted[i + 1]] = x
    return positions
