#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unified ledger for outbound I/O the kernel is still waiting on."""

from __future__ import annotations

from mas.runtime.kernel.state import QProduct
from mas.runtime.kernel.types import InflightKind, OutboundWait, ScheduledEgress


def _sync_legacy_inflight_ids(q: QProduct) -> None:
    q.inflight_correlation_ids = [w.correlation_id for w in q.outbound_waits]


def register_outbound_wait(
    q: QProduct,
    correlation_id: int,
    *,
    kind: InflightKind,
    op: ScheduledEgress | str = "NONE",
) -> None:
    if correlation_id <= 0:
        return
    wait = OutboundWait(correlation_id=correlation_id, kind=kind, op=op)
    for index, existing in enumerate(q.outbound_waits):
        if existing.correlation_id == correlation_id:
            q.outbound_waits[index] = wait
            _sync_legacy_inflight_ids(q)
            return
    q.outbound_waits.append(wait)
    _sync_legacy_inflight_ids(q)


def dismiss_outbound_wait(q: QProduct, correlation_id: int) -> None:
    if correlation_id <= 0:
        return
    q.outbound_waits = [w for w in q.outbound_waits if w.correlation_id != correlation_id]
    _sync_legacy_inflight_ids(q)
    if q.pending_engine_correlation_id == correlation_id:
        q.pending_engine_correlation_id = 0


def clear_outbound_waits(q: QProduct) -> None:
    q.outbound_waits.clear()
    q.inflight_correlation_ids.clear()
    q.pending_engine_correlation_id = 0


def pending_outbound_waits(q: QProduct) -> list[OutboundWait]:
    return list(q.outbound_waits)


def pending_correlation_ids(q: QProduct) -> list[int]:
    if q.outbound_waits:
        return [w.correlation_id for w in q.outbound_waits]
    if q.pending_engine_correlation_id > 0:
        return [q.pending_engine_correlation_id]
    return list(q.inflight_correlation_ids)


def has_pending_outbound(q: QProduct, *, kind: InflightKind | None = None) -> bool:
    waits = q.outbound_waits
    if not waits and q.pending_engine_correlation_id > 0:
        return kind in (None, "MODEL")
    if kind is None:
        return bool(waits) or q.pending_engine_correlation_id > 0
    return any(w.kind == kind for w in waits)


def is_outbound_pending(q: QProduct, correlation_id: int) -> bool:
    if correlation_id <= 0:
        return False
    if any(w.correlation_id == correlation_id for w in q.outbound_waits):
        return True
    return q.pending_engine_correlation_id > 0 and correlation_id == q.pending_engine_correlation_id
