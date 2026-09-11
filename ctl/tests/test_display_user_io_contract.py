#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ConversationDisplayUserIOContract routes inform_user() progress updates through
ConversationDisplay.on_system(), instead of the default registry fallback nothing in
ctl ever reads."""

from __future__ import annotations

from mas.ctl.session.display_user_io_contract import ConversationDisplayUserIOContract


class _RecordingDisplay:
    def __init__(self) -> None:
        self.system_messages: list[str] = []

    def on_system(self, message: str) -> None:
        self.system_messages.append(message)


def test_send_progress_update_renders_via_on_system() -> None:
    display = _RecordingDisplay()
    contract = ConversationDisplayUserIOContract(display)

    result = contract.send_progress_update(
        message="working on it",
        session_id="sess-1",
        agent_id="finance-agent",
        correlation_id=1,
        requesting_user_id="jordan",
        involved_agents=["research-agent"],
        metadata={"step": 1},
    )

    assert result is None
    assert display.system_messages == ["[finance-agent] working on it"]
