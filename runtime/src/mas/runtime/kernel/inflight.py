#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Inflight engine I/O correlation tracking — parallel tool calls + stale discard."""

from __future__ import annotations

from mas.runtime.kernel.state import QProduct


def register_inflight(q: QProduct, correlation_id: int) -> None:
    if correlation_id <= 0:
        return
    if correlation_id not in q.inflight_correlation_ids:
        q.inflight_correlation_ids.append(correlation_id)


def clear_inflight(q: QProduct) -> None:
    q.inflight_correlation_ids.clear()
    q.pending_engine_correlation_id = 0


def dismiss_inflight(q: QProduct, correlation_id: int) -> None:
    q.inflight_correlation_ids = [c for c in q.inflight_correlation_ids if c != correlation_id]
    if q.pending_engine_correlation_id == correlation_id:
        q.pending_engine_correlation_id = 0


def is_inflight(q: QProduct, correlation_id: int) -> bool:
    if q.inflight_correlation_ids:
        return correlation_id in q.inflight_correlation_ids
    return q.pending_engine_correlation_id > 0 and correlation_id == q.pending_engine_correlation_id


def pending_for_validate(q: QProduct) -> list[int]:
    if q.inflight_correlation_ids:
        return list(q.inflight_correlation_ids)
    if q.pending_engine_correlation_id > 0:
        return [q.pending_engine_correlation_id]
    return []
