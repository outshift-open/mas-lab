#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Σ_out — immutable egress symbols leaving the kernel."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from mas.runtime.schema.hitl import HitlQuestionType, HitlResolveChoice


class EgressKind(str, Enum):
    INVOKE_ENGINE_IO = "INVOKE_ENGINE_IO"
    EMIT_CLIENT_RESPONSE = "EMIT_CLIENT_RESPONSE"
    EMIT_HITL_REQUEST = "EMIT_HITL_REQUEST"
    RAISE_BOUNDARY_ERROR = "RAISE_BOUNDARY_ERROR"
    REQUEST_CTX_ASSEMBLY = "REQUEST_CTX_ASSEMBLY"
    NO_OP = "NO_OP"


class InvokeEngineIo(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[EgressKind.INVOKE_ENGINE_IO] = EgressKind.INVOKE_ENGINE_IO
    correlation_id: int = Field(ge=1)
    op: Literal["LLM_CALL", "TOOL_CALL", "MEMORY_OP", "TRANSPORT_MSG"]
    destructive: bool = False


class EmitClientResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[EgressKind.EMIT_CLIENT_RESPONSE] = EgressKind.EMIT_CLIENT_RESPONSE
    content: str = ""
    finish_reason: Literal["stop", "error", "cancelled"] = "stop"


class RaiseBoundaryError(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[EgressKind.RAISE_BOUNDARY_ERROR] = EgressKind.RAISE_BOUNDARY_ERROR
    code: str
    recoverable: bool = True
    message: str = ""


class RequestCtxAssembly(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[EgressKind.REQUEST_CTX_ASSEMBLY] = EgressKind.REQUEST_CTX_ASSEMBLY
    collect_id: str = "default"
    operator_context: str = ""


class EmitHitlRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[EgressKind.EMIT_HITL_REQUEST] = EgressKind.EMIT_HITL_REQUEST
    request_id: int = Field(ge=1)
    question_type: HitlQuestionType = HitlQuestionType.CONFIRM
    question: str = ""
    choices: list[str] = Field(default_factory=list)
    pending_schedule: Literal["NONE", "LLM_CALL", "TOOL_CALL", "MEMORY_OP", "TRANSPORT_MSG"] = "NONE"
    offered_actions: list[HitlResolveChoice] = Field(default_factory=list)
    context_data: dict = Field(default_factory=dict)


class NoOp(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal[EgressKind.NO_OP] = EgressKind.NO_OP


EgressSymbol = Annotated[
    Union[
        InvokeEngineIo,
        EmitClientResponse,
        EmitHitlRequest,
        RaiseBoundaryError,
        RequestCtxAssembly,
        NoOp,
    ],
    Field(discriminator="kind"),
]
