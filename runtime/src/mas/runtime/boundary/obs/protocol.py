#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability sink protocol — M_obs append-only boundary log."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mas.runtime.schema.egress import EgressSymbol
from mas.runtime.schema.ingress import IngressSymbol
from mas.runtime.kernel.state import QProduct


@runtime_checkable
class ObservabilitySink(Protocol):
    """M_obs — record ingress/egress for 3As audit (TLA: Observability.tla)."""

    def record_ingress(self, event: IngressSymbol, q: QProduct) -> None: ...

    def record_egress(self, sym: EgressSymbol, q: QProduct) -> None: ...
