#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kernel outbound-wait ledger."""

from __future__ import annotations

from mas.runtime.kernel.inflight import (
    clear_inflight,
    dismiss_inflight,
    is_inflight,
    pending_for_validate,
    register_inflight,
)
from mas.runtime.kernel.outbound_waits import (
    has_pending_outbound,
    pending_outbound_waits,
    register_outbound_wait,
)
from mas.runtime.kernel.state import QProduct


def test_register_and_dismiss_model_wait() -> None:
    q = QProduct()
    register_outbound_wait(q, 3, kind="MODEL", op="LLM_CALL")
    assert has_pending_outbound(q, kind="MODEL")
    assert pending_for_validate(q) == [3]
    assert is_inflight(q, 3)
    dismiss_inflight(q, 3)
    assert not has_pending_outbound(q)
    assert pending_for_validate(q) == []


def test_parallel_tool_waits_tracked_together() -> None:
    q = QProduct()
    register_inflight(q, 4, kind="TOOL", op="TOOL_CALL")
    register_inflight(q, 5, kind="TOOL", op="TOOL_CALL")
    assert pending_for_validate(q) == [4, 5]
    dismiss_inflight(q, 4)
    assert pending_for_validate(q) == [5]
    assert has_pending_outbound(q, kind="TOOL")


def test_hitl_wait_registers_on_gov_hold() -> None:
    from mas.runtime.machines.gov import gov_clear_hitl, gov_enter_hitl_pending

    q = QProduct()
    gov_enter_hitl_pending(q, request_id=9, pending_schedule="TOOL_CALL")
    waits = pending_outbound_waits(q)
    assert len(waits) == 1
    assert waits[0].kind == "HITL"
    assert waits[0].op == "TOOL_CALL"
    gov_clear_hitl(q)
    assert not has_pending_outbound(q, kind="HITL")


def test_clear_inflight_clears_ledger() -> None:
    q = QProduct()
    register_inflight(q, 1, kind="MODEL", op="LLM_CALL")
    register_inflight(q, 2, kind="TOOL", op="TOOL_CALL")
    clear_inflight(q)
    assert q.outbound_waits == []
    assert q.inflight_correlation_ids == []
