#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Simulated execution engine — mirrors TLA EngineEnvironment.SimulatedNextStep."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


class SimMode(str, Enum):
    DEFAULT = "DEFAULT"
    MEMORY_PROBE = "MEMORY_PROBE"
    TRANSPORT_PROBE = "TRANSPORT_PROBE"


def simulated_next_step(sim_mode: SimMode, correlation_id: int) -> str:
    if sim_mode in {SimMode.MEMORY_PROBE, SimMode.TRANSPORT_PROBE}:
        return "DELEGATE" if correlation_id == 1 else "STOP"
    return "STOP" if correlation_id % 2 == 0 else "TOOL_CALL"


@dataclass
class SimulatedEngine:
    """Deterministic engine adapter for tests and driver loops."""

    sim_mode: SimMode = SimMode.DEFAULT
    script: dict[int, EngineIoReturn] = field(default_factory=dict)
    llm_next_step: Callable[[int], str] | None = None
    llm_tool_intent: Callable[[int], tuple[str, dict]] | None = None

    def exchange_preview(self, op: str) -> str:
        if op == "LLM_CALL":
            return f"simulated:{self.sim_mode.value}"
        return ""

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if io.correlation_id in self.script:
            return self.script[io.correlation_id]

        if io.op == "LLM_CALL":
            if self.llm_next_step is not None:
                next_step = self.llm_next_step(io.correlation_id)
            else:
                next_step = simulated_next_step(self.sim_mode, io.correlation_id)
            tool_name = ""
            tool_arguments: dict = {}
            if next_step == "TOOL_CALL" and self.llm_tool_intent is not None:
                tool_name, tool_arguments = self.llm_tool_intent(io.correlation_id)
            elif next_step == "TOOL_CALL":
                tool_name = ""
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step=next_step,  # type: ignore[arg-type]
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                text="" if next_step == "TOOL_CALL" else f"[simulated model response cid={io.correlation_id}]",
            )

        if io.op == "TOOL_CALL":
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TOOL_RESULT",
                next_step="STOP",
                text=f"[simulated tool result cid={io.correlation_id}]",
            )

        if io.op == "MEMORY_OP":
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
            )

        if io.op == "TRANSPORT_MSG":
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TRANSPORT_ACK",
                next_step="STOP",
            )

        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="ERROR",
            next_step="STOP",
        )
