#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""RecorderContract — structured transition/event recording boundary."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from mas.runtime.contracts.base import CapabilityContract


class RecorderContract(CapabilityContract):
    """Emit and optionally query structured observability events.

    Plugins implement this contract to provide JSONL, OTel, or other backends.
    The kernel and observability plugins **produce** events; recorders **consume**.
    """

    contract_id = "recorder"

    @abstractmethod
    def emit(self, event: dict[str, Any]) -> None:
        """Record one event (TransitionEvent.to_dict() or native kind dict)."""

    def flush(self) -> None:
        """Flush buffered output."""

    def close(self) -> None:
        """Release resources."""

    def query(
        self,
        *,
        kind: str | None = None,
        agent_id: str | None = None,
        call_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Optional read-back; default empty."""
        return []
