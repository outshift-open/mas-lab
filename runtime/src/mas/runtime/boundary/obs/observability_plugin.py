#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ObservabilityPlugin — read-only base for all telemetry export plugins."""

from __future__ import annotations

from typing import ClassVar

from mas.runtime.boundary.obs.transition import TransitionEvent
from mas.runtime.contracts.base import CapabilityContract


class ObservabilityPlugin(CapabilityContract):
    """Subscribe to contract transitions in **read mode** (never blocks execution).

    All export plugins (native JSONL, OTel, audit) inherit from this class.
    The kernel notifies subscribers on every boundary append via
    ``ObservabilityOperator``.
    """

    contract_id = "observability"
    mode: ClassVar[str] = "read"

    def on_transition(self, event: TransitionEvent) -> None:
        """Handle one Mealy boundary transition. Override in subclasses."""

    def flush(self) -> None:
        """Flush buffered export output (override in plugins that buffer)."""

    def close(self) -> None:
        """Release export resources after a run (defaults to flush)."""
        self.flush()

    def attach_agent(self, agent: object) -> None:
        super().attach_agent(agent)
        self._agent_id = getattr(agent, "agent_id", self.agent_id)
