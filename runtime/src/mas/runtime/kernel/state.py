#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kernel product state — Q (control tuple) and run ledger (shared turn data)."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.runtime.kernel.types import (
    CtxState,
    DpState,
    GovState,
    InflightKind,
    LifecycleState,
    MemoryState,
    ModelState,
    ScheduledEgress,
    SessionState,
    ToolState,
    TransportState,
)

# Formal docs use τ for the shared tape; in code we call it the run ledger.

__all__ = [
    "CtxState",
    "DpState",
    "GovState",
    "InflightKind",
    "LifecycleState",
    "MemoryState",
    "ModelState",
    "QProduct",
    "RunEvent",
    "RunLedger",
    "ScheduledEgress",
    "SessionState",
    "ToolState",
    "TransportState",
]


@dataclass
class RunEvent:
    """One ingress event appended during a turn (correlation id + engine return)."""

    correlation_id: int
    response_kind: str
    next_step: str
    text: str = ""


@dataclass
class RunLedger:
    """Ordered run events for the current turn (formal τ tape)."""

    events: list[RunEvent] = field(default_factory=list)
    _allocated_high: int = 0

    @property
    def records(self) -> list[RunEvent]:
        """Alias for tests and trace replay."""
        return self.events

    def next_correlation_id(self) -> int:
        if self._allocated_high > 0:
            return self._allocated_high + 1
        return (self.events[-1].correlation_id + 1) if self.events else 1

    def allocate_correlation_id(self) -> int:
        cid = self.next_correlation_id()
        self._allocated_high = cid
        return cid

    def _sync_allocated(self, correlation_id: int) -> None:
        self._allocated_high = max(self._allocated_high, correlation_id)

    def append(self, record: RunEvent) -> None:
        if self.events and record.correlation_id < self.events[-1].correlation_id:
            raise ValueError("run ledger correlation ids must be monotonic")
        self.events.append(record)
        self._sync_allocated(record.correlation_id)

    def append_inflight(self, record: RunEvent) -> None:
        if any(r.correlation_id == record.correlation_id for r in self.events):
            raise ValueError("duplicate run ledger correlation id")
        self.events.append(record)
        self.events.sort(key=lambda row: row.correlation_id)
        self._sync_allocated(record.correlation_id)


@dataclass
class QProduct:
    ctrl: LifecycleState = LifecycleState.RUNNING
    dp: DpState = DpState.IDLE
    model: ModelState = ModelState.IDLE
    tool: ToolState = ToolState.IDLE
    ctx: CtxState = CtxState.IDLE
    memory: MemoryState = MemoryState.IDLE
    session: SessionState = SessionState.IDLE
    transport: TransportState = TransportState.IDLE
    scheduled_egress: ScheduledEgress = "NONE"
    inflight_kind: InflightKind = "NONE"
    hitl_request_id: int = 0
    hitl_pending_schedule: ScheduledEgress = "NONE"
    hitl_question_type: str = ""
    hitl_gov_override: bool = False
    cot_pass: int = 0
    gov_retry_count: int = 0
    tool_blacklisted: bool = False
    gov_state: str = "IDLE"
    obs_state: str = "IDLE"
    hitl_skip_committed: bool = False
    hitl_block_committed: bool = False
    hitl_tools_approved_turn: bool = False
    hitl_results_approved_turn: bool = False
    hitl_pending_ingress: str = ""
    pending_ingress_return: dict = field(default_factory=dict)
    control_phase: str = "IDLE"
    pending_engine_correlation_id: int = 0
    inflight_correlation_ids: list[int] = field(default_factory=list)
    pending_tool_name: str = ""
    pending_tool_args: dict = field(default_factory=dict)
    pending_tools_by_cid: dict[int, tuple[str, dict]] = field(default_factory=dict)
    parallel_tool_batch: list[dict] = field(default_factory=list)
    dp_data: dict = field(default_factory=dict)
