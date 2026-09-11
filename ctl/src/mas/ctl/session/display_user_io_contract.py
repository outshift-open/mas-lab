#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ConversationDisplayUserIOContract — routes agent-initiated inform_user() progress
updates through the CLI's own ConversationDisplay, instead of the default
RegistryUserIOContract (a fire-and-forget registry entry nothing in ctl ever reads).

Without this, `inform_user()` progress messages were invisible in `mas-ctl chat` --
silently registered and never displayed."""

from __future__ import annotations

from typing import Any

from mas.ctl.ui.display import ConversationDisplay


class ConversationDisplayUserIOContract:
    """UserIOContract that renders progress updates via ConversationDisplay.on_system()."""

    def __init__(self, display: ConversationDisplay) -> None:
        self._display = display

    def send_progress_update(
        self,
        *,
        message: str,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        requesting_user_id: str,
        involved_agents: list[str],
        metadata: dict[str, Any],
    ) -> None:
        self._display.on_system(f"[{agent_id}] {message}")


__all__ = ["ConversationDisplayUserIOContract"]
