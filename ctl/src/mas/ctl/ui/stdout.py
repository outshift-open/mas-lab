#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stdout conversation display — ctl chat UI."""

from __future__ import annotations

import sys

from mas.runtime.schema.egress import EmitHitlRequest

from mas.ctl.run_progress import print_answer
from mas.ctl.ui.display import ConversationDisplay


class StdoutConversationDisplay:
    """Print user/agent turns; quiet mode uses compact final answer only."""

    def __init__(
        self,
        *,
        out: object = sys.stdout,
        err: object = sys.stderr,
        agent_label: str = "Agent",
        verbose: int = 0,
        show_labels: bool = True,
        user_prompt_echoed: bool = False,
    ) -> None:
        self._out = out
        self._err = err
        self._agent_label = agent_label
        self._verbose = verbose
        self._show_labels = show_labels or verbose >= 1
        self._user_prompt_echoed = user_prompt_echoed

    def on_user(self, text: str, *, turn_id: str = "") -> None:
        if self._user_prompt_echoed:
            return
        if self._verbose >= 1 or self._show_labels:
            self._out.write(f"You: {text}\n")
            self._out.flush()

    def on_agent(self, text: str) -> None:
        if not text.strip():
            return
        if self._verbose == 0 and not self._show_labels:
            print_answer(text)
            return
        self._out.write(f"{self._agent_label}: {text}\n\n")
        self._out.flush()

    def on_turn_error(self, message: str, *, detail: str = "") -> None:
        text = (message or "").strip()
        if not text:
            return
        line = f"Error: {text}"
        if self._verbose == 0 and not self._show_labels:
            print_answer(line)
            return
        self._out.write(f"{line}\n")
        if detail.strip() and detail.strip() != text and self._verbose >= 1:
            self._out.write(f"  detail: {detail.strip()}\n")
        self._out.write("\n")
        self._out.flush()

    def on_hitl_request(self, request: EmitHitlRequest) -> None:
        from mas.runtime.boundary.hitl.presentation import format_hitl_brief

        self._err.write("\n── HITL ──\n")
        self._err.write(format_hitl_brief(request) + "\n")
        self._err.flush()

    def on_working(self, message: str = "Agent working…") -> None:
        """Visible progress while the kernel runs (verbose only)."""
        if self._verbose >= 2:
            self._err.write(f"\r\033[K{message}")
            self._err.flush()

    def end_working(self) -> None:
        if self._verbose >= 2:
            self._err.write("\r\033[K")
            self._err.flush()

    def on_system(self, message: str) -> None:
        if self._verbose >= 2:
            self._err.write(f"── {message} ──\n")
            self._err.flush()

    def on_error(self, message: str) -> None:
        self.on_turn_error(message)


def as_display(d: StdoutConversationDisplay) -> ConversationDisplay:
    return d
