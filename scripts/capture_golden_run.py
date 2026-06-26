#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Capture golden-run artifacts (events.jsonl + trace-cache backup) for CI parity."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _capture_one(
    experiment: Path,
    label: str,
    output_root: Path,
) -> int:
    from mas.lab.benchmark.golden.cache_backup import (
        backup_events_golden,
        backup_trace_cache,
        find_events_in_tree,
    )
    from mas.lab.benchmark.golden.events import events_fingerprint, normalize_events_file
    from mas.lab.benchmark.worker import run_benchmark_sync

    import tempfile

    if not experiment.is_file():
        print(f"skip {label}: missing {experiment}", file=sys.stderr)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix=f"golden-{label}-"))
    out = tmp / "benchmark-out"
    trace_cache = tmp / "trace-cache"
    trace_cache.mkdir()
    mas_home = tmp / "mas-home"
    mas_home.mkdir()
    os.environ["MAS_HOME"] = str(mas_home)

    ok = run_benchmark_sync(
        experiment,
        force=True,
        single_run=True,
        max_runs=1,
        output_dir=out,
        trace_cache_dir=trace_cache,
    )
    if not ok:
        print(f"benchmark run failed for {label}", file=sys.stderr)
        return 1

    events_paths = find_events_in_tree(out) or find_events_in_tree(trace_cache)
    if not events_paths:
        print(f"no events.jsonl found for {label}", file=sys.stderr)
        return 1

    events_path = events_paths[0]
    golden_dir = output_root / label
    backup_events_golden(events_path, golden_dir, also_cache_entry=None)
    backup_trace_cache(trace_cache, golden_dir / "cache-backup", label=label)

    fp = events_fingerprint(normalize_events_file(events_path))
    (golden_dir / "events.sha256").write_text(fp + "\n", encoding="utf-8")
    print(f"Captured golden run → {golden_dir}")
    print(f"  events: {events_path}")
    print(f"  fingerprint: {fp}")
    return 0


def main() -> int:
    from mas.lab.benchmark.golden.labs import DEFAULT_MANIFEST, resolve_lab_targets

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment",
        type=Path,
        default=None,
        help="Single experiment YAML (default: lab-smoke fixture when no --labs)",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Golden fixture label (default: derived from experiment path)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "tests/fixtures/golden-runs",
    )
    parser.add_argument(
        "--labs-manifest",
        type=Path,
        default=ROOT / DEFAULT_MANIFEST,
        help="YAML manifest of lab labels → experiment paths",
    )
    parser.add_argument(
        "--labs",
        action="append",
        default=[],
        metavar="LAB",
        help=(
            "Lab to capture (repeatable): manifest label, path to experiment.yaml, "
            "path to *.lab directory, or 'all' for every entry in --labs-manifest"
        ),
    )
    args = parser.parse_args()

    if args.labs:
        try:
            targets = resolve_lab_targets(
                args.labs,
                root=ROOT,
                manifest_path=args.labs_manifest,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(exc, file=sys.stderr)
            return 1
        if not targets:
            print("no lab targets resolved", file=sys.stderr)
            return 1
        rc = 0
        for label, experiment in targets:
            print(f"\n=== lab: {label} ===")
            if _capture_one(experiment, label, args.output_root) != 0:
                rc = 1
        return rc

    experiment = args.experiment or (ROOT / "tests/fixtures/lab-smoke/experiment.yaml")
    label = args.label
    if not label:
        from mas.lab.benchmark.golden.labs import default_label_for

        label = default_label_for(experiment.resolve(), root=ROOT)
    return _capture_one(experiment, label, args.output_root)


if __name__ == "__main__":
    raise SystemExit(main())
