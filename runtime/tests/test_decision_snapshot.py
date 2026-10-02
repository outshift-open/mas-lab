#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from dataclasses import replace

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.envelope import EnvelopeContext, run_egress_authorize_envelope
from mas.runtime.kernel.state import QProduct
from mas.runtime.schema.envelope import ContractKind


def test_governance_authorize_takes_one_decision_snapshot() -> None:
    seen: list[tuple[str, str, str]] = []

    def sink(*, hook: str, decision: str, correlation_id: int, op: str, tool_name: str) -> None:
        seen.append((hook, decision, op))

    q = QProduct()
    q.pending_tool_name = "lookup"
    ctx = EnvelopeContext(
        q=q,
        correlation_id=1,
        contract=ContractKind.TOOL,
        scheduled_op="TOOL_CALL",
        config=replace(KernelConfig(hitl_on_tool=False), on_decision_snapshot=sink),
        tool_name="lookup",
    )
    run_egress_authorize_envelope(ctx)
    assert seen == [("egress", "ALLOW", "TOOL_CALL")]
