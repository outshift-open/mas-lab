#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_gov — governance Mealy δ (Governance.tla). HITL lives here only."""

from __future__ import annotations

from mas.runtime.kernel.state import QProduct, ScheduledEgress
from mas.runtime.kernel.types import GovState


def gov_is_hitl_pending(q: QProduct) -> bool:
    return q.gov_state == GovState.HITL_PENDING.value and q.hitl_request_id > 0


def gov_enter_hitl_pending(
    q: QProduct,
    *,
    request_id: int,
    pending_schedule: ScheduledEgress,
    question_type: str = "CONFIRM",
) -> None:
    q.gov_state = GovState.HITL_PENDING.value
    q.hitl_request_id = request_id
    q.hitl_pending_schedule = pending_schedule
    q.hitl_question_type = question_type


def gov_clear_hitl(q: QProduct) -> None:
    q.hitl_request_id = 0
    q.hitl_pending_schedule = "NONE"
    q.hitl_question_type = ""
    if q.gov_state == GovState.HITL_PENDING.value:
        q.gov_state = GovState.IDLE.value


def gov_on_hitl_schedule(q: QProduct) -> None:
    q.gov_state = GovState.AUTHZ_EGRESS.value


def gov_on_egress_allowed(q: QProduct) -> None:
    q.gov_state = GovState.VALIDATING.value


def gov_on_idle(q: QProduct) -> None:
    q.gov_state = GovState.IDLE.value
