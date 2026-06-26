#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Plan-and-Execute design pattern — TLA: DesignPatternScheduler.tla, PlanExecutePattern.tla."""

from __future__ import annotations

import json
import re
from typing import Any

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.egress_gate import emit_scheduled_egress
from mas.runtime.kernel.response_text import response_text_from_run
from mas.runtime.machines.design_pattern.plugins.react import ReactPlugin
from mas.runtime.schema.egress import EgressSymbol, EmitClientResponse, NoOp
from mas.runtime.schema.ingress import IngressSymbol, UserInputReceived
from mas.runtime.kernel.state import DpState, QProduct, RunLedger

_PHASE_PLAN = "PLAN"
_PHASE_ACT = "ACT"
_PHASE_SYNTH = "SYNTH"
_PHASE_REPLAN = "REPLAN"


def _parse_plan(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        stripped = fence.group(1).strip()
    for candidate in (stripped,):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "plan" in parsed:
                return list(parsed["plan"])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        m = re.search(pattern, stripped)
        if m:
            try:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict) and "plan" in parsed:
                    return list(parsed["plan"])
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                continue
    return []


class PlanExecutePlugin(ReactPlugin):
    plugin_id = "plan_execute@v1"

    def protocol_lines(self, q: QProduct | None) -> list[str]:
        phase = (q.dp_data.get("phase") if q else None) or _PHASE_PLAN
        if phase == _PHASE_SYNTH:
            return [
                "=== PLAN-AND-EXECUTE: FINAL SYNTHESIS ===",
                "All planned steps executed. Write a complete user-facing answer from tool results above.",
            ]
        if phase in (_PHASE_PLAN, _PHASE_REPLAN):
            return [
                "=== PLAN-AND-EXECUTE PROTOCOL ===",
                'Output ONLY JSON: {"plan": [{"tool": "name", "arguments": {...}}, ...]}',
                "No markdown fences. Every step must use an available tool name.",
            ]
        return []

    def handle_event(
        self,
        q: QProduct,
        run: RunLedger,
        event: IngressSymbol,
        *,
        config: KernelConfig,
    ) -> list[EgressSymbol]:
        if isinstance(event, UserInputReceived) and q.dp == DpState.IDLE:
            q.dp_data = {"phase": _PHASE_PLAN, "plan": [], "executed_idx": 0, "failures": 0}
        return super().handle_event(q, run, event, config=config)

    def _evaluate(self, q: QProduct, run: RunLedger, config: KernelConfig) -> list[EgressSymbol]:
        if q.dp != DpState.EVALUATING or not run.events:
            return [NoOp()]
        last = run.events[-1]
        phase = str(q.dp_data.get("phase") or _PHASE_PLAN)

        if phase == _PHASE_PLAN and last.response_kind in ("MODEL_TEXT", "ERROR"):
            plan = _parse_plan(last.text)
            if not plan:
                prose = last.text.strip() or "No plan generated."
                q.dp = DpState.IDLE
                return [EmitClientResponse(content=prose, finish_reason="stop")]
            q.dp_data["plan"] = plan
            q.dp_data["phase"] = _PHASE_ACT
            q.dp_data["executed_idx"] = 0
            return self._schedule_plan_step(q, run, config, index=0)

        if phase == _PHASE_REPLAN and last.response_kind in ("MODEL_TEXT", "ERROR"):
            plan = _parse_plan(last.text)
            if plan:
                q.dp_data["plan"] = plan
                q.dp_data["phase"] = _PHASE_ACT
                q.dp_data["executed_idx"] = 0
                return self._schedule_plan_step(q, run, config, index=0)
            q.dp_data["phase"] = _PHASE_SYNTH
            return self._schedule_llm(q, run, config)

        if phase == _PHASE_ACT and last.response_kind == "TOOL_RESULT":
            idx = int(q.dp_data.get("executed_idx") or 0) + 1
            q.dp_data["executed_idx"] = idx
            plan = q.dp_data.get("plan") or []
            if idx < len(plan):
                return self._schedule_plan_step(q, run, config, index=idx)
            q.dp_data["phase"] = _PHASE_SYNTH
            return self._schedule_llm(q, run, config)

        if phase == _PHASE_SYNTH and last.response_kind in ("MODEL_TEXT", "ERROR"):
            q.dp = DpState.IDLE
            content = last.text.strip() or response_text_from_run(run, fallback="Done.")
            finish = "error" if last.response_kind == "ERROR" else "stop"
            return [EmitClientResponse(content=content, finish_reason=finish)]  # type: ignore[arg-type]

        if last.next_step == "TOOL_CALL" and config.hitl_on_tool:
            return super()._evaluate(q, run, config)

        return super()._evaluate(q, run, config)

    def _schedule_plan_step(
        self, q: QProduct, run: RunLedger, config: KernelConfig, *, index: int
    ) -> list[EgressSymbol]:
        plan = q.dp_data.get("plan") or []
        if index >= len(plan):
            q.dp_data["phase"] = _PHASE_SYNTH
            return self._schedule_llm(q, run, config)
        step = plan[index]
        q.pending_tool_name = str(step.get("tool") or "tool")
        q.pending_tool_args = dict(step.get("arguments") or {})
        q.scheduled_egress = "TOOL_CALL"
        q.dp = DpState.EGRESS_PENDING
        return emit_scheduled_egress(q, run, config)

    def _schedule_llm(
        self, q: QProduct, run: RunLedger, config: KernelConfig
    ) -> list[EgressSymbol]:
        q.scheduled_egress = "LLM_CALL"
        q.dp = DpState.EGRESS_PENDING
        return emit_scheduled_egress(q, run, config)
