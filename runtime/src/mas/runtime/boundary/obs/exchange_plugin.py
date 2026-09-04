#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ExchangePlugin \u2014 read-only, multi-subscriber interface for the driver's
exchange log (the display-oriented USER<->AGENT<->LLM<->TOOL record stream).

Mirrors ObservabilityPlugin's additive subscribe() pattern (see
observability_plugin.py) but for ExchangeRecord \u2014 the driver's own,
already-complete six-tag exchange stream (USER->AGENT, AGENT->USER,
AGENT->LLM, LLM->AGENT, AGENT->TOOL, TOOL->AGENT) used for human-facing
trace/log display. Consumers subscribe via
KernelDriver.subscribe_exchange(plugin) instead of overwriting a single
driver.on_exchange callback \u2014 multiple subscribers (e.g. mas-ctl's own CLI
trace plugin and an external chat-UI plugin) can coexist without one
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
