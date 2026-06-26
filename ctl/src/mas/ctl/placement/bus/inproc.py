#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-process CommBus — local-monolith flavour (N runtimes, one process)."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.ctl.placement.bus.protocol import CommBus, CommEndpoint
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


@dataclass
class InProcessCommBus:
    """Zero-copy local routing between RuntimeInstance endpoints."""

    _endpoints: dict[str, CommEndpoint] = field(default_factory=dict)

    def register(self, agent_id: str, endpoint: CommEndpoint) -> None:
        self._endpoints[agent_id] = endpoint

    def resolve_address(self, agent_id: str) -> str:
        return f"inproc://{agent_id}"

    def send(
        self, *, from_agent: str, to_agent: str, intent: InvokeEngineIo
    ) -> EngineIoReturn | None:
        target = self._endpoints.get(to_agent)
        if target is None:
            return EngineIoReturn(
                correlation_id=intent.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
            )
        result = EngineIoReturn(
            correlation_id=intent.correlation_id,
            response_kind="TRANSPORT_ACK",
            next_step="STOP",
        )
        target.deliver(result)
        return result
