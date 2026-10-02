#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Product recipes as compositions of ControlContract — no new kernel ops."""

from __future__ import annotations

from typing import Iterable

DEFAULT_WRITE_TOOLS = ("write", "edit", "bash", "shell")


def apply_plan_mode(
    control: object,
    session_id: str,
    *,
    write_tools: Iterable[str] = DEFAULT_WRITE_TOOLS,
) -> int:
    """Pause and disable write tools. Live spec, not a second loop."""
    pause = getattr(control, "pause")
    disable = getattr(control, "disable_tool")
    pause(session_id, reason="plan_mode")
    revision = 0
    for name in write_tools:
        try:
            revision = int(disable(session_id, name=name, reason="plan_mode"))
        except ValueError:
            continue
    return revision


def apply_default_mode(control: object, session_id: str) -> None:
    """Leave tools as restored; resume the session."""
    getattr(control, "resume")(session_id)
