#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared helpers for lifecycle-control lab pipeline figure steps."""
from __future__ import annotations

from pathlib import Path


def resolve_path(raw: str, output_dir: Path) -> Path:
    return Path(str(raw).replace("{output_dir}", str(output_dir))).expanduser()


def resolve_trace_path(raw: str, output_dir: Path) -> Path:
    """Resolve a trace path, following ``.run_ref`` when symlinks are stale."""
    path = resolve_path(raw, output_dir)
    if path.is_file():
        return path
    if path.name == "events.jsonl" and path.parent.name == "traces":
        from mas.lab.benchmark.cache.trace_store import resolve_run_events_path

        resolved = resolve_run_events_path(path.parent.parent)
        if resolved is not None:
            return resolved
    return path
