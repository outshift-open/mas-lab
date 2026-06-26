#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Migrate topologies-trip-planner run dirs so that benchmark run discovers them
as local cache hits, skipping agent re-execution.

For each of the 50 run dirs in ~/.mas-lab/labs/topologies-trip-planner/:
  - Removes the broken traces/ symlink → creates a real traces/events.jsonl sentinel
  - Removes the broken run_info.json symlink (benchmark will rewrite it)
  - Copies metrics.json from the design-space-lab counterpart (if available)

After migration, running:
  mas-lab benchmark run labs/design-space.lab/02-topologies/experiment.yaml

will detect _local_hit for each run and skip agent execution.
Then eval_mce (with overwrite: false) reuses the existing metrics.json.
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

SRC_ROOT = Path.home() / ".mas-lab" / "design-space-lab"
DST_ROOT = Path.home() / ".mas-lab" / "labs" / "topologies-trip-planner"

# Minimal JSONL event — non-empty so _local_hit fires
SENTINEL_EVENT = json.dumps({
    "event": "session_start",
    "timestamp": "2026-05-21T00:00:00Z",
    "note": "legacy-run-sentinel — original traces were in design-space-lab",
}) + "\n"

ok = skipped = missing_metrics = 0

for run_dir in sorted(DST_ROOT.glob("topo-*/item*/r*")):
    # ── Identify counterpart in design-space-lab ──────────────────────────
    # e.g. topo-linear-pipeline/itemc1/r1
    scenario = run_dir.parts[-3]
    item_dir_name = run_dir.parts[-2]   # itemc1
    run_idx_dir = run_dir.parts[-1]     # r1
    src_run = SRC_ROOT / scenario / item_dir_name / run_idx_dir

    # ── Fix traces/ ───────────────────────────────────────────────────────
    traces_link = run_dir / "traces"
    if traces_link.is_symlink():
        traces_link.unlink()
    elif traces_link.exists() and traces_link.is_dir():
        events = traces_link / "events.jsonl"
        if events.exists() and not events.is_symlink() and events.stat().st_size > 0:
            skipped += 1
            continue  # already a valid local hit

    traces_link.mkdir(parents=True, exist_ok=True)
    events_file = traces_link / "events.jsonl"
    events_file.write_text(SENTINEL_EVENT)

    # ── Fix run_info.json symlink ─────────────────────────────────────────
    run_info = run_dir / "run_info.json"
    if run_info.is_symlink():
        run_info.unlink()
    # Leave any real run_info.json intact; benchmark will overwrite via _write_run_info

    # ── Copy metrics.json from design-space-lab ───────────────────────────
    src_metrics = src_run / "metrics.json"
    dst_metrics = run_dir / "metrics.json"
    if src_metrics.exists() and not dst_metrics.exists():
        shutil.copy2(src_metrics, dst_metrics)
        print(f"  ✓ metrics.json  {scenario}/{item_dir_name}/{run_idx_dir}")
    elif not src_metrics.exists():
        missing_metrics += 1
        print(f"  ⚠ no src metrics {scenario}/{item_dir_name}/{run_idx_dir}")

    ok += 1

print(f"\nDone: {ok} migrated, {skipped} already valid, {missing_metrics} missing src metrics")
