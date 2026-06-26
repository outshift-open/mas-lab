#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_session — session checkpoint Mealy δ (SessionMachine.tla)."""

from __future__ import annotations

from mas.runtime.kernel.state import SessionState


def session_on_checkpoint(state: SessionState) -> SessionState:
    if state == SessionState.IDLE:
        return SessionState.CHECKPOINTING
    return state


def session_on_done(state: SessionState) -> SessionState:
    if state == SessionState.CHECKPOINTING:
        return SessionState.IDLE
    return state


def session_on_abort(state: SessionState) -> SessionState:
    return SessionState.IDLE
