#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Inflight engine I/O correlation tracking — backed by ``outbound_waits``."""

from __future__ import annotations

from mas.runtime.kernel.outbound_waits import (
    clear_outbound_waits,
    dismiss_outbound_wait,
    is_outbound_pending,
    pending_correlation_ids,
    register_outbound_wait,
)
from mas.runtime.kernel.state import QProduct
from mas.runtime.kernel.types import InflightKind, ScheduledEgress


def register_inflight(
    q: QProduct,
    correlation_id: int,
    *,
    kind: InflightKind = "TOOL",
    op: ScheduledEgress | str = "NONE",
) -> None:
    register_outbound_wait(q, correlation_id, kind=kind, op=op)


def clear_inflight(q: QProduct) -> None:
    clear_outbound_waits(q)


def dismiss_inflight(q: QProduct, correlation_id: int) -> None:
    dismiss_outbound_wait(q, correlation_id)


def is_inflight(q: QProduct, correlation_id: int) -> bool:
    return is_outbound_pending(q, correlation_id)


def pending_for_validate(q: QProduct) -> list[int]:
    return pending_correlation_ids(q)
