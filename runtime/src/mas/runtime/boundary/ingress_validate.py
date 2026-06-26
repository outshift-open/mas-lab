#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress governance validation — mirrors TLA Governance.IngressGovernanceValid."""

from __future__ import annotations

from mas.runtime.schema.ingress import EngineIoReturn, IngressSymbol

_RESPONSE_KINDS = frozenset({"MODEL_TEXT", "TOOL_RESULT", "TRANSPORT_ACK", "ERROR"})
_NEXT_STEP_VALUES = frozenset(
    {"STOP", "TOOL_CALL", "PARALLEL_TOOL_CALLS", "LLM_CALL", "DELEGATE"}
)


def ingress_governance_valid(
    event: EngineIoReturn,
    *,
    last_correlation_id: int = 0,
    pending_correlation_id: int = 0,
    inflight_correlation_ids: list[int] | None = None,
) -> bool:
    if event.response_kind not in _RESPONSE_KINDS:
        return False
    if event.correlation_id <= 0 or event.next_step not in _NEXT_STEP_VALUES:
        return False
    inflight = inflight_correlation_ids or []
    if inflight:
        return event.correlation_id in inflight
    if pending_correlation_id > 0 and event.correlation_id != pending_correlation_id:
        return False
    return last_correlation_id == 0 or event.correlation_id > last_correlation_id


def validate_ingress(
    event: IngressSymbol,
    *,
    last_correlation_id: int = 0,
    pending_correlation_id: int = 0,
    inflight_correlation_ids: list[int] | None = None,
) -> bool:
    if isinstance(event, EngineIoReturn):
        return ingress_governance_valid(
            event,
            last_correlation_id=last_correlation_id,
            pending_correlation_id=pending_correlation_id,
            inflight_correlation_ids=inflight_correlation_ids,
        )
    return True
