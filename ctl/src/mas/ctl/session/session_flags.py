#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Validate CLI session flags against manifest-derived session requirements."""

from __future__ import annotations

import sys
from typing import Any

import click


def validate_chat_session(
    *,
    interactive: bool,
    single_turn: bool,
    scripted_turns: list[str],
    manifest: dict[str, Any] | None,
    is_tty: bool | None = None,
) -> None:
    """Reject inconsistent flag combinations before blocking on stdin."""
    tty = sys.stdin.isatty() if is_tty is None else is_tty
    hitl_mode = _hitl_mode(manifest)

    if interactive and not tty and not scripted_turns:
        raise click.UsageError(
            "-i/--interactive requires a TTY, or provide input via -q/-p or stdin pipe."
        )

    if hitl_mode == "interactive" and not tty and not scripted_turns:
        raise click.UsageError(
            "spec.governance.hitl_mode is 'interactive' but stdin is not a TTY. "
            "Use hitl_mode: auto-approve in the overlay for CI/batch runs, "
            "or pass -q with a scripted query."
        )

    if hitl_mode == "interactive" and single_turn and scripted_turns and not tty:
        raise click.UsageError(
            "Non-interactive single-turn run with hitl_mode: interactive will block "
            "without an operator. Set hitl_mode: auto-approve in the governance overlay."
        )


def _hitl_mode(manifest: dict[str, Any] | None) -> str | None:
    from mas.ctl.manifest.spec_bindings import parse_governance

    spec = (manifest or {}).get("spec") or {}
    gov = parse_governance(spec.get("governance"))
    if not gov.hitl_on_tool and not gov.hitl_on_tool_result:
        return None
    mode = gov.hitl_mode
    return str(mode).strip().lower() if mode else "interactive"
