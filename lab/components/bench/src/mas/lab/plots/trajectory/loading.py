#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Trace loading helpers."""

import json
from pathlib import Path
from typing import Union

# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def _find_trace_by_run_id(run_id: str) -> Path:
    """Search the runs root for a run directory whose name contains *run_id*.

    The runs root is resolved via :func:`mas.lab.paths.runs_root`:
    ``MAS_RUNS_ROOT`` > ``MAS_DATA_ROOT/runs`` > ``~/.mas-lab/runs``.
    """
    from mas.lab import paths as _paths
    runs_root = _paths.runs_root()
    if not runs_root.exists():
        raise FileNotFoundError(f"{runs_root} not found; cannot resolve run_id '{run_id}'")
    # walk one level deep: {runs_root}/<mas_name>/<run_dir>/traces/events.jsonl
    for mas_dir in runs_root.iterdir():
        if not mas_dir.is_dir():
            continue
        for run_dir in mas_dir.iterdir():
            if run_id in run_dir.name:
                candidate = run_dir / "traces" / "events.jsonl"
                if candidate.exists():
                    return candidate
    raise FileNotFoundError(f"No trace found for run_id '{run_id}' under {runs_root}")


def load_trace(source: Union[str, Path]) -> list[dict]:
    """Load events from a ``.jsonl`` trace file, a ``kg.json`` file, or a run_id.

    Parameters
    ----------
    source:
        * Absolute or relative path to a ``.jsonl`` file, **or**
        * Absolute or relative path to a ``kg.json`` file (auto-detected by
          extension; converted to synthetic events via :func:`kg_to_events`), **or**
        * A run_id string (e.g. ``"20260224-062142-baseline-673d6359"``); the
          function will search the runs root (``MAS_RUNS_ROOT`` /
          ``MAS_DATA_ROOT/runs`` / ``~/.mas-lab/runs``) for matching directories.

    Returns
    -------
    list[dict]
        Parsed event dicts, with invalid/blank lines silently skipped.
    """
    path = Path(source).expanduser()
    if not path.exists():
        # Try run_id resolution
        path = _find_trace_by_run_id(str(source))

    # Auto-detect kg.json and convert to events
    if path.suffix == ".json":
        from mas.lab.plots.kg_adapter import load_kg, kg_to_events
        kg = load_kg(path)
        return kg_to_events(kg)

    events: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events
