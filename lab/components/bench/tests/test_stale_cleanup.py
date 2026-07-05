#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from mas.lab.benchmark.stale_cleanup import (
    clean_stale_scenarios,
    collect_trace_cache_refs,
    find_stale_scenario_dirs,
    hashes_orphaned_after_removal,
)


def _write_run(output_dir: Path, scenario: str, item: str, run: str, run_hash: str) -> Path:
    run_dir = output_dir / scenario / item / run
    run_dir.mkdir(parents=True)
    (run_dir / ".run_ref").write_text(run_hash + "\n", encoding="utf-8")
    return run_dir


def test_find_stale_scenario_dirs(tmp_path: Path) -> None:
    out = tmp_path / "bench"
    _write_run(out, "baseline", "item1", "r1", "aaa")
    _write_run(out, "full", "item1", "r1", "bbb")
    stale = find_stale_scenario_dirs(out, ["baseline"])
    assert [p.name for p in stale] == ["full"]


def test_orphaned_trace_cache_only_when_unreferenced(tmp_path: Path) -> None:
    out = tmp_path / "bench"
    other = tmp_path / "other-bench"
    run_a = _write_run(out, "full", "item1", "r1", "shared")
    _write_run(other, "keep", "item1", "r1", "shared")
    _write_run(out, "full", "item1", "r2", "solo")

    refs = collect_trace_cache_refs([tmp_path])
    assert refs["shared"] == 2
    assert refs["solo"] == 1

    orphaned = hashes_orphaned_after_removal([out / "full"], [tmp_path])
    assert orphaned == ["solo"]

    tc_root = tmp_path / "trace-cache"
    (tc_root / "solo").mkdir(parents=True)
    (tc_root / "solo" / "traces").mkdir()
    (tc_root / "shared").mkdir(parents=True)

    report = clean_stale_scenarios(
        out,
        ["baseline"],
        experiment_yaml=tmp_path / "experiment.yaml",
        trace_cache_dir=tc_root,
        dry_run=False,
        search_roots=[tmp_path],
    )
    assert [p.name for p in report.removed_scenario_dirs] == ["full"]
    assert report.removed_trace_cache_hashes == ["solo"]
    assert (tc_root / "solo").exists() is False
    assert (tc_root / "shared").exists() is True
    assert run_a.parent.parent.exists() is False
