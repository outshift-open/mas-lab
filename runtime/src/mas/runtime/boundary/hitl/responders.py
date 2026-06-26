#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HITL operator responders — implementations of the HitlResponder contract.

Contract: ``resolve(EmitHitlRequest) -> HitlResolve`` (see ``schema/egress`` + ``schema/ingress``).

- **In-process** responders are wired on ``KernelDriver.hitl`` (auto-approve, tests).
- **Interactive** operators terminate at the ctl surface (``OperatorConsole`` / curses TUI) when
  the driver has no in-process responder — kernel pauses with M_gov=HITL_PENDING until ctl feeds
  ``HitlResolve``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from mas.runtime.schema.egress import EmitHitlRequest
from mas.runtime.schema.hitl import HitlResolveChoice
from mas.runtime.schema.ingress import HitlResolve


class HitlResponder(Protocol):
    def resolve(self, request: EmitHitlRequest) -> HitlResolve: ...


def _pick_offered(
    request: EmitHitlRequest,
    preferences: tuple[HitlResolveChoice, ...],
    fallback: HitlResolveChoice,
) -> HitlResolveChoice:
    offered = set(request.offered_actions)
    for choice in preferences:
        if choice in offered:
            return choice
    if offered:
        return next(iter(offered))
    return fallback


@dataclass
class AutoApproveResponder:
    """Always approve — prefers ALLOW then SCHEDULE from offered actions."""

    operator_id: str = "auto-approver"

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        resolution = _pick_offered(
            request,
            (HitlResolveChoice.ALLOW, HitlResolveChoice.SCHEDULE),
            HitlResolveChoice.ALLOW,
        )
        return HitlResolve(
            request_id=request.request_id,
            resolution=resolution,
            operator_context={"operator_id": self.operator_id},
        )


@dataclass
class AutoDenyResponder:
    """Always block — prefers BLOCK then SKIP."""

    operator_id: str = "auto-denier"

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        resolution = _pick_offered(
            request,
            (HitlResolveChoice.BLOCK, HitlResolveChoice.SKIP),
            HitlResolveChoice.BLOCK,
        )
        return HitlResolve(
            request_id=request.request_id,
            resolution=resolution,
            operator_context={"operator_id": self.operator_id},
        )


@dataclass
class AutoTerminateResponder:
    operator_id: str = "auto-terminator"

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        return HitlResolve(
            request_id=request.request_id,
            resolution=HitlResolveChoice.TERMINATE,
            operator_context={"operator_id": self.operator_id},
        )


@dataclass
class SkipWithSteeringResponder:
    """Skip pending tool and inject operator steering into context rebuild."""

    steering: str
    operator_id: str = "trip-planner-operator"

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        return HitlResolve(
            request_id=request.request_id,
            resolution=HitlResolveChoice.SKIP,
            operator_context={
                "operator_id": self.operator_id,
                "steering": self.steering,
                "tool": request.context_data.get("tool", ""),
            },
        )


@dataclass
class ScriptedHitlResponder:
    """Map request_id → resolution; optional default for unscripted requests."""

    script: dict[int, HitlResolveChoice] = field(default_factory=dict)
    default: HitlResolveChoice = HitlResolveChoice.SCHEDULE
    operator_id: str = "scripted"

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        resolution = self.script.get(request.request_id, self.default)
        return HitlResolve(
            request_id=request.request_id,
            resolution=resolution,
            operator_context={"operator_id": self.operator_id},
        )


@dataclass(frozen=True)
class OperatorPersona:
    """Named operator with resolution preferences."""

    operator_id: str
    preferences: tuple[HitlResolveChoice, ...] = (
        HitlResolveChoice.ALLOW,
        HitlResolveChoice.SCHEDULE,
    )
    fallback: HitlResolveChoice = HitlResolveChoice.BLOCK


@dataclass
class MultiOperatorHitlResponder:
    """Route HITL requests to one of several operator personas."""

    operators: dict[str, OperatorPersona] = field(default_factory=dict)
    pick_operator: Callable[[EmitHitlRequest], str] | None = None
    _round_robin_ids: list[str] = field(default_factory=list, init=False)
    _round_robin_idx: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self._round_robin_ids:
            self._round_robin_ids = list(self.operators.keys())

    def resolve(self, request: EmitHitlRequest) -> HitlResolve:
        op_id = self._select_operator(request)
        persona = self.operators.get(op_id)
        if persona is None:
            persona = OperatorPersona(operator_id=op_id)
        resolution = _pick_offered(request, persona.preferences, persona.fallback)
        return HitlResolve(
            request_id=request.request_id,
            resolution=resolution,
            operator_context={"operator_id": persona.operator_id},
        )

    def _select_operator(self, request: EmitHitlRequest) -> str:
        if self.pick_operator is not None:
            return self.pick_operator(request)
        ctx_op = request.context_data.get("operator_id")
        if isinstance(ctx_op, str) and ctx_op in self.operators:
            return ctx_op
        if not self._round_robin_ids:
            return "default"
        op_id = self._round_robin_ids[self._round_robin_idx % len(self._round_robin_ids)]
        self._round_robin_idx += 1
        return op_id
