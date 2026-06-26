#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compact single-line progress for non-verbose CLI runs (v1 parity)."""

from __future__ import annotations

import shutil
import sys

_compact_active: bool = False


def set_run_progress(verbosity: int) -> None:
    global _compact_active
    _compact_active = verbosity == 0


def is_active() -> bool:
    return _compact_active


def _terminal_width() -> int:
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def _pad_to_width(text: str, cols: int) -> str:
    if len(text) >= cols:
        return text[: cols - 1] + "…"
    return text + (" " * (cols - len(text)))


def clear_line() -> None:
    if not _compact_active:
        return
    cols = _terminal_width()
    sys.stderr.write("\r" + (" " * cols) + "\r")
    sys.stderr.flush()


def emit(agent_id: str, event: str, detail: str = "") -> None:
    if not _compact_active:
        return
    prefix = f"[{agent_id}] " if agent_id else ""
    text = f"{prefix}{event}"
    if detail:
        text = f"{text} {detail}"
    cols = _terminal_width()
    sys.stderr.write("\r" + _pad_to_width(text, cols))
    sys.stderr.flush()


def finish() -> None:
    if not _compact_active:
        return
    clear_line()
    sys.stderr.write("\n")
    sys.stderr.flush()


def print_answer(text: str) -> None:
    if not _compact_active:
        print(text, flush=True)
        return
    clear_line()
    cols = _terminal_width()
    lines = text.splitlines() or [""]
    sys.stdout.write("\r" + _pad_to_width(lines[0], cols))
    if len(lines) == 1:
        sys.stdout.write("\n")
    else:
        sys.stdout.write("\n" + "\n".join(lines[1:]) + "\n")
    sys.stdout.flush()
