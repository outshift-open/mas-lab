#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Parallel tool egress — multiple TOOL_CALL intents in one agentic step."""

from __future__ import annotations

from mas.runtime.boundary.gov.telemetry import get_bound_observability
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import apply_control_tool_request
from mas.runtime.kernel.egress_gate import emit_scheduled_egress, schedule_tool_egress
from mas.runtime.kernel.inflight import register_inflight
from mas.runtime.schema.egress import EgressSymbol, EmitHitlRequest, InvokeEngineIo, RaiseBoundaryError
from mas.runtime.schema.ingress import ToolCallSpec
from mas.runtime.kernel.state import DpState, QProduct, RunLedger


def schedule_parallel_tools_egress(
    q: QProduct,
    run: RunLedger,
    config: KernelConfig,
    tools: list[ToolCallSpec],
) -> list[EgressSymbol]:
    """Run gov/chokepoint per tool; emit parallel InvokeEngineIo when all allowed."""
    if not tools:
        return schedule_tool_egress(q, run, config)
    if not config.parallel_tool_calls or len(tools) == 1:
        first = tools[0]
        q.pending_tool_name = first.tool_name
        q.pending_tool_args = dict(first.tool_arguments)
        return schedule_tool_egress(q, run, config)

    out: list[EgressSymbol] = []
    q.pending_tools_by_cid.clear()
    # Snapshot the enclosing frame ONCE, before any of these N tools' own
    # contract_call/start fires below (each iteration's emit_scheduled_egress
    # steps CONTRACT_START synchronously) — otherwise each sibling reads
    # whatever the PREVIOUS sibling just pushed as its parent, chaining them
    # onto each other instead of the frame that's actually enclosing all of
    # them. See ObservabilityOperator.begin_sibling_batch.
    obs = get_bound_observability()
    if obs is not None:
        obs.begin_sibling_batch(len(tools))
    for spec in tools:
        q.pending_tool_name = spec.tool_name
        q.pending_tool_args = dict(spec.tool_arguments)
        apply_control_tool_request(q)
        batch = emit_scheduled_egress(q, run, config)
        if any(isinstance(sym, (RaiseBoundaryError, EmitHitlRequest)) for sym in batch):
            return batch
        for sym in batch:
            if isinstance(sym, InvokeEngineIo) and sym.op == "TOOL_CALL":
                register_inflight(q, sym.correlation_id)
                q.pending_tools_by_cid[sym.correlation_id] = (
                    spec.tool_name,
                    dict(spec.tool_arguments),
                )
                out.append(sym)
    q.scheduled_egress = "NONE"
    q.dp = DpState.AWAITING_INGRESS
    q.inflight_kind = "TOOL"
    return out
