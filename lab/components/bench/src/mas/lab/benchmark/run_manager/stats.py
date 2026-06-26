#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""Benchmark run statistics helpers."""

from pathlib import Path
from typing import Dict, Optional

from mas.lab import paths as _paths

def count_cached_runs(run_dir: Path, trace_cache_root: Optional[Path] = None) -> tuple[int, int]:
    """Return (cached, total) run counts for *run_dir*.

    Walks *run_dir* for all ``run_info.json`` paths (including broken symlinks
    that indicate a run whose trace cache is not yet available), reads each
    ``run_hash``, and checks whether the corresponding entry exists under
    *trace_cache_root*.
    """
    import json as _json
    if trace_cache_root is None:
        trace_cache_root = _paths.trace_cache()
    total = 0
    cached = 0
    for run_info_path in run_dir.rglob("run_info.json"):
        # Count the path regardless of whether the target exists (handles broken symlinks)
        total += 1
        try:
            data = _json.loads(run_info_path.read_text())
            run_hash = data.get("run_hash")
            if run_hash and (trace_cache_root / run_hash).exists():
                cached += 1
        except Exception:
            logger.debug('suppressed', exc_info=True)
    return cached, total


def read_quality_stats(run_dir: Path) -> Optional[Dict[str, int]]:
    """Return W/E quality statistics from results.csv in *run_dir*.

    Looks for a ``results.csv`` (or ``results/results.csv``) containing the
    ``run_status`` column written by the ``collect_metrics`` pipeline step.
    Counts unique (scenario, item_id, run_idx) tuples per ``run_status`` value.

    Returns ``{"ok": N, "warn": N, "error": N, "total": N}`` or ``None`` when
    no usable CSV is found.
    """
    import csv as _csv

    candidates = [
        run_dir / "results.csv",
        run_dir / "results" / "results.csv",
    ]
    csv_path: Optional[Path] = None
    for c in candidates:
        if c.exists():
            csv_path = c
            break
    if csv_path is None:
        return None

    try:
        counts: Dict[str, int] = {"ok": 0, "warn": 0, "error": 0}
        seen: set = set()
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = _csv.DictReader(fh)
            if "run_status" not in (reader.fieldnames or []):
                return None
            for row in reader:
                key = (row.get("scenario", ""), row.get("item_id", ""), row.get("run_idx", ""))
                if key in seen:
                    continue
                seen.add(key)
                status = row.get("run_status", "ok")
                counts[status] = counts.get(status, 0) + 1
        counts["total"] = sum(counts.values())
        return counts
    except Exception:
        return None
