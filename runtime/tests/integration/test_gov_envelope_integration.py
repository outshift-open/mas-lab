#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""GovEnvelopeMachine + observability integration."""

from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.kernel.envelope import EnvelopeContext
from mas.runtime.kernel.state import QProduct
from mas.runtime.machines.gov_envelope import GovEnvelopeMachine
from mas.runtime.schema.envelope import EnvelopeSymbol
from mas.runtime.schema.observability import ObsEventKind


def _ctx() -> EnvelopeContext:
    return EnvelopeContext(
        q=QProduct(),
        correlation_id=1,
        contract="TOOL",
        scheduled_op="TOOL_CALL",
        observability=ObservabilityOperator(),
        gov_decision="ALLOW",
    )


def test_gov_envelope_records_authorize_lifecycle():
    machine = GovEnvelopeMachine()
    ctx = _ctx()
    machine.step(EnvelopeSymbol.GOV_AUTHORIZE_START, ctx)
    machine.step(EnvelopeSymbol.GOVERNANCE_AUTHORIZE, ctx)
    machine.step(EnvelopeSymbol.GOV_AUTHORIZE_END, ctx)
    kinds = [e.kind for e in ctx.observability.events]  # type: ignore[union-attr]
    assert ObsEventKind.GOVERNANCE_DECISION in kinds
