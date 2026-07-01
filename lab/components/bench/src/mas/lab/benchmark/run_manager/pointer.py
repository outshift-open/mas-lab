#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Last-run pointer file helpers."""

from pathlib import Path

from mas.runtime.xdg import mas_state_root

# Canonical write target (XDG state dir).
def last_run_write_path() -> Path:
    return mas_state_root() / "last-run.json"


def resolve_last_run_file() -> Path | None:
    """Return the last-run pointer file when present (XDG state dir)."""
    canonical = last_run_write_path()
    return canonical if canonical.is_file() else None
