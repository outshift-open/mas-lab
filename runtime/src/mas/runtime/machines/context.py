#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_ctx — context assembly Mealy δ (ContextMachine.tla)."""

from __future__ import annotations

from mas.runtime.kernel.state import CtxState, DpState


def ctx_on_user_input(state: CtxState) -> CtxState:
    return CtxState.COLLECTING


def ctx_on_assembly_complete(state: CtxState) -> CtxState:
    if state == CtxState.COLLECTING:
        return CtxState.COMMITTED
    return state


def ctx_on_cycle_reset(state: CtxState) -> CtxState:
    if state == CtxState.COMMITTED:
        return CtxState.IDLE
    return state


def ctx_on_abort(state: CtxState) -> CtxState:
    return CtxState.IDLE


def ctx_collecting_when_building(ctx: CtxState, dp: DpState) -> bool:
    if dp == DpState.CTX_BUILD:
        return ctx == CtxState.COLLECTING
    return True
