#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability operator integration."""

from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.schema.observability import ObsEventKind, ObsPhase


def test_observability_records_envelope_and_governance():
    obs = ObservabilityOperator()
    obs.record_envelope_activity(
        symbol="TOOL_CALL_START",
        activity="enter",
        boundary="egress",
        phase=ObsPhase.AUTHZ,
        correlation_id=1,
    )
    obs.record_governance_decision(
        hook="egress",
        phase="after",
        decision="ALLOW",
        correlation_id=1,
    )
    kinds = {e.kind for e in obs.events}
    assert ObsEventKind.ENVELOPE_ACTIVITY in kinds
    assert ObsEventKind.GOVERNANCE_DECISION in kinds
