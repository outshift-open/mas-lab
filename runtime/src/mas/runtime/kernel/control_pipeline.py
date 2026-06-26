#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Control Mealy — tool-call pipeline (REQUEST→…→VALID) coupled to agentic loop.

Maps the Contracts & Control slide:
  REQUEST → INGRESS → AUTHZ → EXECUTE → RESULT → EGRESS → VALID

The agentic loop (M_dp) THINK/ACT is *blocked* at AWAITING_INGRESS until this
pipeline reaches VALID (or IDLE). Coupling rules enforce that — machines do not
embed cross-pipeline writes.
"""

from __future__ import annotations

from enum import Enum

from mas.runtime.kernel.state import DpState, QProduct, ToolState


class ControlPhase(str, Enum):
    IDLE = "IDLE"
    REQUEST = "REQUEST"
    INGRESS = "INGRESS"
    AUTHZ = "AUTHZ"
    EXECUTE = "EXECUTE"
    RESULT = "RESULT"
    EGRESS = "EGRESS"
    VALID = "VALID"


def control_phase_of(q: QProduct) -> ControlPhase:
    raw = getattr(q, "control_phase", ControlPhase.IDLE.value)
    try:
        return ControlPhase(raw)
    except ValueError:
        return ControlPhase.IDLE


def set_control_phase(q: QProduct, phase: ControlPhase) -> None:
    q.control_phase = phase.value


def control_on_tool_request(q: QProduct) -> None:
    """Agentic loop schedules tool egress → control REQUEST."""
    set_control_phase(q, ControlPhase.REQUEST)


def control_on_chokepoint_enter(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.INGRESS)


def control_on_authz(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.AUTHZ)


def control_on_execute(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.EXECUTE)


def control_on_result(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.RESULT)


def control_on_egress_gov(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.EGRESS)


def control_on_valid(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.VALID)


def control_on_idle(q: QProduct) -> None:
    set_control_phase(q, ControlPhase.IDLE)


def agentic_act_blocked(q: QProduct) -> bool:
    """True when M_dp ACT→CONTEXT must wait for control pipeline completion."""
    if q.dp != DpState.AWAITING_INGRESS:
        return False
    phase = control_phase_of(q)
    if phase in {ControlPhase.IDLE, ControlPhase.VALID}:
        return False
    if q.tool == ToolState.WAIT_GOV:
        return True
    return phase not in {ControlPhase.IDLE, ControlPhase.VALID}


def may_agentic_evaluate(q: QProduct) -> bool:
    """EVALUATING / CONTEXT only when control pipeline is not mid-flight."""
    phase = control_phase_of(q)
    if phase in {ControlPhase.IDLE, ControlPhase.VALID}:
        return True
    if q.tool in {ToolState.WAIT_GOV, ToolState.EXECUTING}:
        return False
    return phase in {ControlPhase.RESULT, ControlPhase.EGRESS}
