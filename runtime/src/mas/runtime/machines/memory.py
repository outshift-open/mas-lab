#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_mem — memory store Mealy δ (MemoryMachine.tla)."""

from __future__ import annotations

from mas.runtime.kernel.state import MemoryState, ScheduledEgress


def memory_on_egress_start(state: MemoryState, op: ScheduledEgress) -> MemoryState:
    if op == "MEMORY_OP":
        return MemoryState.QUERYING
    return state


def memory_on_ingress(state: MemoryState) -> MemoryState:
    if state in {MemoryState.QUERYING, MemoryState.WRITING}:
        return MemoryState.DONE
    return state


def memory_on_evaluate(state: MemoryState) -> MemoryState:
    if state == MemoryState.DONE:
        return MemoryState.IDLE
    return state


def memory_on_reset(state: MemoryState) -> MemoryState:
    return MemoryState.IDLE
