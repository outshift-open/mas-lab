#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""InteractiveHitlContract — resolves agent-initiated request_human_input() calls by
prompting the operator directly at the terminal, mirroring OperatorConsole's stdin-prompt
pattern for the older, separate governance-triggered HITL (see hitl_prompt.py).

Without this, `mas-ctl chat -i` had no resolver for request_human_input() at all: the
default RegistryHitlContract would register the request and block forever, since nothing
in an interactive CLI session ever calls HitlResolverRegistry.resolve()."""

from __future__ import annotations

import sys
from typing import Any, Callable, TextIO


def _match_choice(raw: str, choices: list[str]) -> str:
    if not choices or raw in choices:
        return raw
    matched = next((choice for choice in choices if choice.lower() == raw.lower()), None)
    return matched if matched is not None else raw


class InteractiveHitlContract:
    """HITLContract that asks the operator directly at the terminal.

    `timeout` is accepted (per the HITLContract protocol) but ignored -- a
    synchronous stdin prompt has no meaningful way to time out; the operator
    is expected to answer.
    """

    def __init__(
        self,
        *,
        read_line: Callable[[str], str] | None = None,
        out: TextIO | None = None,
    ) -> None:
        self._read_line = read_line or input
        self._out = out or sys.stderr

    def request_approval(
        self,
        *,
        question: str,
        session_id: str,
        requesting_user_id: str,
        agent_id: str,
        correlation_id: int,
        question_type: str,
        choices: list[str],
        context_data: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self._out.write(f"\n── {agent_id} needs your input ──\n{question}\n")
        if context_data:
            self._out.write(f"Context: {context_data}\n")
        if choices:
            self._out.write(f"Choices: {', '.join(choices)}\n")
        self._out.flush()

        prompt = "Your response: " if not choices else f"Your response ({'/'.join(choices)}): "
        choice = _match_choice((self._read_line(prompt) or "").strip(), choices)
        return {"choice": choice, "steering": ""}


__all__ = ["InteractiveHitlContract"]
