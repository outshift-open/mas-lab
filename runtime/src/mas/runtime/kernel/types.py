#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared kernel type symbols — no imports from machines (breaks import cycles)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

class LifecycleState(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class DpState(str, Enum):
    IDLE = "IDLE"
    CTX_BUILD = "CTX_BUILD"
    EGRESS_PENDING = "EGRESS_PENDING"
    AWAITING_INGRESS = "AWAITING_INGRESS"
    EVALUATING = "EVALUATING"


class ModelState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    CALLING = "CALLING"
    DONE = "DONE"
    ERROR = "ERROR"


class ToolState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    WAIT_GOV = "WAIT_GOV"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    ERROR = "ERROR"


class CtxState(str, Enum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    COMMITTED = "COMMITTED"


class MemoryState(str, Enum):
    IDLE = "IDLE"
    QUERYING = "QUERYING"
    WRITING = "WRITING"
    DONE = "DONE"


class SessionState(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    CHECKPOINTING = "CHECKPOINTING"


class TransportState(str, Enum):
    IDLE = "IDLE"
    SENDING = "SENDING"
    AWAITING_ACK = "AWAITING_ACK"


class GovState(str, Enum):
    IDLE = "IDLE"
    AUTHZ_EGRESS = "AUTHZ_EGRESS"
    AUTHZ_INGRESS = "AUTHZ_INGRESS"
    HITL_PENDING = "HITL_PENDING"
    VALIDATING = "VALIDATING"
    BLOCKED = "BLOCKED"


InflightKind = Literal["NONE", "MODEL", "TOOL"]
ScheduledEgress = Literal["NONE", "LLM_CALL", "TOOL_CALL", "MEMORY_OP", "TRANSPORT_MSG"]
