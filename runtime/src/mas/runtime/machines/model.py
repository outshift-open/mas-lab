#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_model — LLM capability Mealy δ (ModelMachine.tla)."""

from __future__ import annotations

from mas.runtime.kernel.state import ModelState, ScheduledEgress


def model_may_start_egress(state: ModelState) -> bool:
    return state == ModelState.IDLE


def model_on_egress(state: ModelState, op: ScheduledEgress) -> ModelState:
    if op == "LLM_CALL":
        return ModelState.CALLING
    return state


def model_on_ingress(state: ModelState, *, response_kind: str) -> ModelState:
    if state != ModelState.CALLING:
        return state
    if response_kind == "ERROR":
        return ModelState.ERROR
    return ModelState.DONE


def model_on_evaluate(state: ModelState) -> ModelState:
    if state == ModelState.DONE:
        return ModelState.IDLE
    return state


def model_on_abort(state: ModelState) -> ModelState:
    return ModelState.IDLE
