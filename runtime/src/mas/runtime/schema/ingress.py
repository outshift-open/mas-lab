#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Σ_in — immutable ingress symbols entering the kernel."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from mas.runtime.schema.hitl import HitlResolveChoice


class IngressKind(str, Enum):
    USER_INPUT_RECEIVED = "USER_INPUT_RECEIVED"
    LIFECYCLE_PAUSE = "LIFECYCLE_PAUSE"
    LIFECYCLE_RESUME = "LIFECYCLE_RESUME"
    LIFECYCLE_ABORT = "LIFECYCLE_ABORT"
    ENGINE_IO_RETURN = "ENGINE_IO_RETURN"
    CTX_ASSEMBLY_COMPLETE = "CTX_ASSEMBLY_COMPLETE"
    HITL_APPROVE = "HITL_APPROVE"
    HITL_RESOLVE = "HITL_RESOLVE"
    OPERATOR_STEER_RECEIVED = "OPERATOR_STEER_RECEIVED"


class UserInputReceived(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.USER_INPUT_RECEIVED] = IngressKind.USER_INPUT_RECEIVED
    user_turn_id: str
    text: str


class LifecyclePause(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.LIFECYCLE_PAUSE] = IngressKind.LIFECYCLE_PAUSE
    reason: str = ""


class LifecycleResume(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.LIFECYCLE_RESUME] = IngressKind.LIFECYCLE_RESUME


class LifecycleAbort(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.LIFECYCLE_ABORT] = IngressKind.LIFECYCLE_ABORT
    reason: str = ""


class ToolCallSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_name: str
    tool_arguments: dict = Field(default_factory=dict)


class EngineIoReturn(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.ENGINE_IO_RETURN] = IngressKind.ENGINE_IO_RETURN
    correlation_id: int = Field(ge=1)
    response_kind: Literal["MODEL_TEXT", "TOOL_RESULT", "TRANSPORT_ACK", "ERROR"] = "MODEL_TEXT"
    next_step: Literal[
        "STOP", "TOOL_CALL", "PARALLEL_TOOL_CALLS", "LLM_CALL", "DELEGATE"
    ] = "STOP"
    tool_name: str = ""
    tool_arguments: dict = Field(default_factory=dict)
    parallel_tools: tuple[ToolCallSpec, ...] = ()
    text: str = ""


class CtxAssemblyComplete(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.CTX_ASSEMBLY_COMPLETE] = IngressKind.CTX_ASSEMBLY_COMPLETE
    collect_id: str = "default"


class HitlApprove(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.HITL_APPROVE] = IngressKind.HITL_APPROVE


class HitlResolve(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.HITL_RESOLVE] = IngressKind.HITL_RESOLVE
    request_id: int = Field(ge=1)
    resolution: HitlResolveChoice
    answer: object | None = None
    operator_context: dict = Field(default_factory=dict)


class OperatorSteerReceived(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[IngressKind.OPERATOR_STEER_RECEIVED] = IngressKind.OPERATOR_STEER_RECEIVED
    steer_id: str = "steer-1"
    context_text: str = ""


IngressSymbol = Annotated[
    Union[
        UserInputReceived,
        LifecyclePause,
        LifecycleResume,
        LifecycleAbort,
        EngineIoReturn,
        CtxAssemblyComplete,
        HitlApprove,
        HitlResolve,
        OperatorSteerReceived,
    ],
    Field(discriminator="kind"),
]
