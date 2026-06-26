#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Gov state machine helper integration."""

from mas.runtime.kernel.state import QProduct
from mas.runtime.machines.gov import (
    gov_clear_hitl,
    gov_enter_hitl_pending,
    gov_is_hitl_pending,
    gov_on_egress_allowed,
    gov_on_idle,
)


def test_gov_hitl_pending_round_trip():
    q = QProduct()
    gov_enter_hitl_pending(q, request_id=99, pending_schedule="TOOL_CALL")
    assert gov_is_hitl_pending(q)
    gov_clear_hitl(q)
    assert not gov_is_hitl_pending(q)


def test_gov_egress_allowed_to_validating():
    q = QProduct()
    gov_on_egress_allowed(q)
    assert q.gov_state == "VALIDATING"
    gov_on_idle(q)
    assert q.gov_state == "IDLE"
