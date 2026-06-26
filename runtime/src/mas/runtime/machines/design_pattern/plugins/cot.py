#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Chain-of-Thought pattern plugin — TLA: CoTPattern.tla."""

from __future__ import annotations

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.egress_gate import emit_scheduled_egress
from mas.runtime.machines.design_pattern.plugins.react import ReactPlugin
from mas.runtime.schema.egress import EgressSymbol, NoOp
from mas.runtime.schema.ingress import IngressSymbol, UserInputReceived
from mas.runtime.kernel.state import CtxState, DpState, ModelState, QProduct, RunLedger, ToolState


class CotPlugin(ReactPlugin):
    plugin_id = "cot@v1"

    def __init__(self) -> None:
        self._max_cot_pass = 1

    def handle_event(
        self,
        q: QProduct,
        run: RunLedger,
        event: IngressSymbol,
        *,
        config: KernelConfig,
    ) -> list[EgressSymbol]:
        if isinstance(event, UserInputReceived) and q.dp == DpState.IDLE:
            q.cot_pass = 0
        return super().handle_event(q, run, event, config=config)

    def _evaluate(self, q: QProduct, run: RunLedger, config: KernelConfig) -> list[EgressSymbol]:
        if q.dp != DpState.EVALUATING or not run.events:
            return [NoOp()]
        last = run.events[-1]
        q.model = ModelState.IDLE if q.model == ModelState.DONE else q.model
        q.tool = ToolState.IDLE if q.tool == ToolState.DONE else q.tool
        q.ctx = CtxState.IDLE

        max_pass = config.max_cot_pass
        if last.next_step == "STOP" and q.cot_pass < max_pass:
            q.cot_pass += 1
            q.scheduled_egress = "LLM_CALL"
            q.dp = DpState.EGRESS_PENDING
            return emit_scheduled_egress(q, run, config)
        return super()._evaluate(q, run, config)
