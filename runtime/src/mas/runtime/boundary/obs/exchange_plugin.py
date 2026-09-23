#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ExchangePlugin — read-only, multi-subscriber interface for the driver's
exchange log (structured USER↔AGENT↔LLM↔TOOL records).

Mirrors ObservabilityPlugin's additive subscribe() pattern (see
observability_plugin.py) but for ExchangeRecord — typed hops
(user_in / user_out / llm_request / llm_response / tool_call / tool_result).
Pretty-print is a view on those fields, not the interchange. Consumers
subscribe via KernelDriver.subscribe_exchange(plugin) instead of overwriting
a single driver.on_exchange callback — multiple subscribers (e.g. mas-ctl's
CLI trace plugin and an external chat-UI plugin) can coexist without one
silently discarding another.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mas.runtime.driver.driver import ExchangeRecord


class ExchangePlugin(ABC):
    """Read-only subscriber for driver ExchangeRecord notifications."""

    @abstractmethod
    def on_exchange(self, record: "ExchangeRecord") -> None:
        """Handle one ExchangeRecord as it is emitted by the driver."""


__all__ = ["ExchangePlugin"]
