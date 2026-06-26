#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_tool — tool capability Mealy δ (ToolMachine.tla).

Cross-machine posture (WAIT_GOV, EXECUTING) is set by M_coord coupling rules;
this module only applies local tool δ.
"""

from __future__ import annotations

from mas.runtime.kernel.state import ScheduledEgress, ToolState


def tool_may_start_egress(state: ToolState) -> bool:
    return state == ToolState.IDLE


def tool_on_egress(state: ToolState, op: ScheduledEgress) -> ToolState:
    if op == "TOOL_CALL":
        return ToolState.EXECUTING
    return state


def tool_on_ingress(state: ToolState, *, response_kind: str) -> ToolState:
    if state != ToolState.EXECUTING:
        return state
    if response_kind == "ERROR":
        return ToolState.ERROR
    return ToolState.DONE


def tool_on_evaluate(state: ToolState) -> ToolState:
    if state == ToolState.DONE:
        return ToolState.IDLE
    return state


def tool_on_abort(state: ToolState) -> ToolState:
    return ToolState.IDLE
