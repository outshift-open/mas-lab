#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HITL operator protocol — implementations are library plugins."""

from __future__ import annotations

from typing import Protocol

from mas.runtime.schema.egress import EmitHitlRequest
from mas.runtime.schema.ingress import HitlResolve


class HitlResponder(Protocol):
    def resolve(self, request: EmitHitlRequest) -> HitlResolve: ...
