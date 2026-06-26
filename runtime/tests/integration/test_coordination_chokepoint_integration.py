#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Chokepoint coordinator integration."""

from mas.runtime.boundary.coordination.chokepoint import ChokepointCoordinator, ObsState
from mas.runtime.kernel.state import QProduct
from mas.runtime.machines.gov import GovState


def test_coordination_egress_governance_transitions():
    coord = ChokepointCoordinator()
    q = QProduct()
    coord.before_egress_governance(q)
    assert coord.gov_state == GovState.AUTHZ_EGRESS
    coord.after_egress_allowed(q)
    assert coord.gov_state == GovState.VALIDATING


def test_coordination_hitl_sets_pending_gov():
    coord = ChokepointCoordinator()
    q = QProduct()
    coord.on_egress_hitl(q)
    assert coord.gov_state == GovState.HITL_PENDING
    assert coord.obs_state in {ObsState.RECORDING, ObsState.IDLE, ObsState.FLUSHING}
