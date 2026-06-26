#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HITL terminals — terminate EMIT_HITL_REQUEST / HITL_RESOLVE at the boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from mas.runtime.schema.egress import EmitHitlRequest
from mas.runtime.schema.hitl import HitlResolveChoice
from mas.runtime.schema.ingress import HitlResolve


class HitlTerminal(Protocol):
    def resolve(self, request: EmitHitlRequest) -> HitlResolve: ...


@dataclass
class ScriptedHitlTerminal:
    """Map request_id → resolution for deterministic runs."""

    script: dict[int, HitlResolveChoice] = field(default_factory=dict)
    default: HitlResolveChoice = HitlResolveChoice.ALLOW
    operator_id: str = "scripted"

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        resolution = self.script.get(request.request_id, self.default)
        return HitlResolve(
            request_id=request.request_id,
            resolution=resolution,
            operator_context={"operator_id": self.operator_id},
        )
