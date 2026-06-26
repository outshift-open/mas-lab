#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Context assembly plug-in protocol — swappable M_ctx boundary adapter."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mas.runtime.schema.egress import RequestCtxAssembly
from mas.runtime.schema.ingress import CtxAssemblyComplete


@runtime_checkable
class CtxAssembler(Protocol):
    """Complete REQUEST_CTX_ASSEMBLY without kernel importing engine."""

    def complete(self, request: RequestCtxAssembly) -> CtxAssemblyComplete: ...
