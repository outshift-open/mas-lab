#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress step unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mas.runtime.boundary.gov.ingress_plugin import IngressGovDecision
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.ingress_step import apply_engine_io_return
from mas.runtime.kernel.state import QProduct, RunLedger
from mas.runtime.schema.egress import NoOp
from mas.runtime.schema.governance import GovernanceAction
from mas.runtime.schema.ingress import EngineIoReturn


def test_apply_engine_io_return_prefers_tool_metadata_for_correlation_id():
    q = QProduct()
    q.inflight_correlation_ids = [42]
    q.pending_tool_name = "tool_a"
    q.pending_tool_args = {"from": "fallback"}
    q.pending_tools_by_cid[42] = ("tool_b", {"from": "by_cid"})

    run = RunLedger()
    event = EngineIoReturn(
        correlation_id=42,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="done",
    )
    config = KernelConfig()

    with patch(
        "mas.runtime.kernel.ingress_step.run_ingress_validate_envelope",
        return_value=IngressGovDecision(action=GovernanceAction.ALLOW),
    ) as env_mock, patch(
        "mas.runtime.kernel.ingress_step.commit_engine_io_return",
        return_value=[NoOp()],
    ) as commit_mock:
        out = apply_engine_io_return(
            q,
            run,
            event,
            config=config,
            evaluate=MagicMock(),
        )

    env_ctx = env_mock.call_args.args[0]
    assert env_ctx.scheduled_op == "TOOL_CALL"
    assert env_ctx.tool_name == "tool_b"
    assert env_ctx.tool_arguments == {"from": "by_cid"}

    commit_mock.assert_called_once()
    assert out == [NoOp()]
