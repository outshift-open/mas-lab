#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Optional stderr hints when ctl terminates boundary protocols (User, HITL, …)."""

from __future__ import annotations

import sys
from typing import Any


def emit_session_protocol_hints(
    *,
    interactive: bool,
    hitl_terminal: Any | None,
    hitl_responder: Any | None,
    verbose: int = 0,
    trace: bool = False,
    trace_timestamps: bool = False,
    trace_engine: bool = False,
    err: Any = sys.stderr,
) -> None:
    """One-line hints on stderr when plugins need ctl boundary termination."""
    if not interactive or verbose < 1:
        return
    hints: list[str] = []
    if trace:
        hints.append(
            "Trace on: exchanges stream on stderr during each turn "
            "(AGENT→LLM→TOOL)."
        )
        if trace_timestamps:
            hints.append("Trace timestamps on (UTC + elapsed per exchange).")
        if trace_engine:
            hints.append("Trace engine I/O on (raw InvokeEngineIo / EngineIoReturn JSON).")
    if hitl_terminal is not None:
        hints.append(
            "HITL scripted terminal wired on controller (tests / automation)."
        )
    elif hitl_responder is not None:
        hints.append(f"HITL in-process responder: {type(hitl_responder).__name__}")
    elif interactive:
        hints.append(
            "Operator console: one prompt at a time; /reset /pause /resume /abort /steer; "
            "HITL when tools require approval."
        )
    for line in hints:
        err.write(f"note: {line}\n")
    err.flush()
