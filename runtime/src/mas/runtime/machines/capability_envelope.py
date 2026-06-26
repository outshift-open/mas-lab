#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_tool / M_model envelope δ — capability posture on contract execute σ."""

from __future__ import annotations

from dataclasses import dataclass

from mas.runtime.machines.model import model_on_egress
from mas.runtime.machines.tool import tool_on_egress
from mas.runtime.schema.envelope import ContractKind, EnvelopeSymbol

from mas.runtime.kernel.envelope import EnvelopeContext


@dataclass
class CapabilityEnvelopeMachine:
    """Steps on CONTRACT_START / CONTRACT_EXECUTE / CONTRACT_END."""

    machine_id: str = "M_capability"

    def step(self, symbol: EnvelopeSymbol, ctx: EnvelopeContext) -> None:
        q = ctx.q
        op = ctx.scheduled_op
        if symbol == EnvelopeSymbol.CONTRACT_START:
            if ctx.contract == ContractKind.TOOL:
                q.tool = tool_on_egress(q.tool, "TOOL_CALL")
            elif ctx.contract == ContractKind.MODEL:
                q.model = model_on_egress(q.model, "LLM_CALL")
            elif ctx.contract == ContractKind.MEMORY:
                from mas.runtime.machines.memory import memory_on_egress_start

                q.memory = memory_on_egress_start(q.memory, "MEMORY_OP")
            elif ctx.contract == ContractKind.TRANSPORT:
                from mas.runtime.machines.transport import transport_on_egress

                q.transport = transport_on_egress(q.transport, "TRANSPORT_MSG")
        elif symbol == EnvelopeSymbol.CONTRACT_END:
            if ctx.contract == ContractKind.TOOL and op == "TOOL_CALL":
                from mas.runtime.machines.tool import tool_on_ingress

                kind = ctx.ingress_event.response_kind if ctx.ingress_event else "TOOL_RESULT"
                q.tool = tool_on_ingress(q.tool, response_kind=kind)
            elif ctx.contract == ContractKind.MODEL and op == "LLM_CALL":
                from mas.runtime.machines.model import model_on_ingress

                kind = ctx.ingress_event.response_kind if ctx.ingress_event else "MODEL_TEXT"
                q.model = model_on_ingress(q.model, response_kind=kind)
            elif ctx.contract == ContractKind.MEMORY and op == "MEMORY_OP":
                from mas.runtime.machines.memory import memory_on_ingress

                q.memory = memory_on_ingress(q.memory)
            elif ctx.contract == ContractKind.TRANSPORT and op == "TRANSPORT_MSG":
                from mas.runtime.machines.transport import transport_on_ingress

                kind = ctx.ingress_event.response_kind if ctx.ingress_event else "TRANSPORT_ACK"
                q.transport = transport_on_ingress(q.transport, response_kind=kind)
