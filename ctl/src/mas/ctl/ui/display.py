#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Conversation display — ctl UI; runtime never prints."""

from __future__ import annotations

from typing import Protocol

from mas.runtime.schema.egress import EmitHitlRequest


class ConversationDisplay(Protocol):
    """Render conversation and control events (stdout, curses, web, …)."""

    def on_user(self, text: str, *, turn_id: str = "") -> None: ...

    def on_agent(self, text: str) -> None: ...

    def on_turn_error(self, message: str, *, detail: str = "") -> None: ...

    def on_hitl_request(self, request: EmitHitlRequest) -> None: ...

    def on_system(self, message: str) -> None: ...

    def on_error(self, message: str) -> None: ...
