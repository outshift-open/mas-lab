#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Fix design-space/topologies-trip-planner run dirs:
1. Write sentinel events.jsonl to empty files (enables _local_hit)
2. Copy metrics.json from design-space-lab/ for the 10 real items per topo

Usage:
    python scripts/fix_design_space_runs.py [--dry-run]
"""
import json
import shutil
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

BASE = Path.home() / ".mas-lab/labs/design-space/topologies-trip-planner"
SRC_BASE = Path.home() / ".mas-lab/design-space-lab"

SENTINEL = json.dumps({
    "event": "session_start",
    "timestamp": "2026-05-21T00:00:00Z",
    "note": "legacy-run-sentinel — original traces were in design-space-lab",
}) + "\n"

TOPOS = [
    "topo-linear-pipeline",
    "topo-moderator-broker",
    "topo-single-agent",
    "topo-supervised",
    "topo-verifier",
]
# Dataset items (s1-s4, c1-c6)
REAL_ITEMS = {f"items{i}" for i in range(1, 5)} | {f"itemc{i}" for i in range(1, 7)}

sentinel_written = 0
metrics_copied = 0
metrics_missing_src = 0
skipped_item0 = 0
errors = 0

for topo in TOPOS:
    tdir = BASE / topo
    src_tdir = SRC_BASE / topo
    if not tdir.exists():
        print(f"[WARN] Missing: {tdir}")
        continue

    for item_dir in sorted(tdir.iterdir()):
        item_name = item_dir.name
        run_dir = item_dir / "r1"
        if not run_dir.exists():
            continue

        # Skip item0 (dummy run from when dataset was missing)
        if item_name == "item0":
            skipped_item0 += 1
            continue

        # --- Fix events.jsonl ---
        ev = run_dir / "traces" / "events.jsonl"
        if ev.exists() and ev.stat().st_size == 0:
            if DRY_RUN:
                print(f"[DRY] Would write sentinel: {ev}")
            else:
                try:
                    ev.write_text(SENTINEL, encoding="utf-8")
                    sentinel_written += 1
                except Exception as exc:
                    print(f"[ERROR] Could not write {ev}: {exc}")
                    errors += 1
        elif not ev.exists():
            print(f"[WARN] events.jsonl missing (no traces dir?): {ev}")

        # --- Copy metrics.json ---
        dst_metrics = run_dir / "metrics.json"
        if not dst_metrics.exists() and item_name in REAL_ITEMS:
            src_metrics = src_tdir / item_name / "r1" / "metrics.json"
            if src_metrics.exists():
                if DRY_RUN:
                    print(f"[DRY] Would copy: {src_metrics} → {dst_metrics}")
                else:
                    try:
                        shutil.copy2(src_metrics, dst_metrics)
                        metrics_copied += 1
                    except Exception as exc:
                        print(f"[ERROR] Could not copy {src_metrics}: {exc}")
                        errors += 1
            else:
                print(f"[WARN] Source metrics missing: {src_metrics}")
                metrics_missing_src += 1

print()
print("=== Summary ===")
print(f"sentinel events.jsonl written: {sentinel_written}")
print(f"metrics.json copied:           {metrics_copied}")
print(f"missing source metrics:        {metrics_missing_src}")
print(f"item0 dirs skipped:            {skipped_item0}")
print(f"errors:                        {errors}")
if DRY_RUN:
    print("\n[DRY RUN — no changes made]")
