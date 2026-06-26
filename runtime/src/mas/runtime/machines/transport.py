#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_trans — transport messaging Mealy δ (TransportMachine.tla)."""

from __future__ import annotations

from mas.runtime.kernel.state import ScheduledEgress, TransportState


def transport_on_egress(state: TransportState, op: ScheduledEgress) -> TransportState:
    if op == "TRANSPORT_MSG":
        return TransportState.SENDING
    return state


def transport_on_ingress(state: TransportState, *, response_kind: str) -> TransportState:
    if state == TransportState.SENDING:
        state = TransportState.AWAITING_ACK
    if state == TransportState.AWAITING_ACK and response_kind == "TRANSPORT_ACK":
        return TransportState.IDLE
    return state


def transport_on_reset(state: TransportState) -> TransportState:
    return TransportState.IDLE
