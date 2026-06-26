#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Structured HITL request/response — mirrors mas-lab policy_engine HITL types."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HitlQuestionType(str, Enum):
    CONFIRM = "CONFIRM"
    FREE_FORM = "FREE_FORM"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    MULTI_SELECT = "MULTI_SELECT"
    FORM = "FORM"


class HitlResolveChoice(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    SCHEDULE = "SCHEDULE"
    TERMINATE = "TERMINATE"
    SKIP = "SKIP"


class HitlRequest(BaseModel):
    """Emitted when operator input is required before continuing."""

    model_config = ConfigDict(frozen=True)
    request_id: int = Field(ge=1)
    policy_name: str = "scheduler"
    question_type: HitlQuestionType = HitlQuestionType.CONFIRM
    question: str = ""
    choices: list[str] = Field(default_factory=list)
    form_fields: dict[str, Any] = Field(default_factory=dict)
    context_data: dict[str, Any] = Field(default_factory=dict)
    pending_schedule: Literal["NONE", "LLM_CALL", "TOOL_CALL", "MEMORY_OP", "TRANSPORT_MSG"] = "NONE"
    offered_actions: list[HitlResolveChoice] = Field(default_factory=list)


class HitlResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: int = Field(ge=1)
    resolution: HitlResolveChoice
    answer: Any = None
    operator_context: dict[str, Any] = Field(default_factory=dict)
