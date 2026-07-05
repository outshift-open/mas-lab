#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Detect and remove stale benchmark output from prior experiment definitions."""

import logging
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

_RESERVED_OUTPUT_NAMES = frozenset({".cache", "metadata.yaml", "results.csv", "state.json"})


@dataclass
class StaleCleanReport:
    """Summary of stale benchmark output handling."""

    stale_scenario_dirs: list[Path] = field(default_factory=list)
    removed_scenario_dirs: list[Path] = field(default_factory=list)
    removed_trace_cache_hashes: list[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass(frozen=True)
class BenchmarkCleanSettings:
    """Workspace defaults for stale benchmark cleanup."""

    clean_stale_outputs: bool = False
    clean_stale_trace_cache: bool = True


def load_benchmark_clean_settings(
    workspace_root: Path | None = None,
) -> BenchmarkCleanSettings:
    """Read ``mas_lab.benchmark.clean_stale_*`` from workspace ``config.yaml``."""
    try:
        from mas.lab.workspace import WorkspaceConfig

        ws = WorkspaceConfig.load(workspace_root or Path.cwd())
        if not ws.found:
            return BenchmarkCleanSettings()
        bench = (ws._data.get("mas_lab") or {}).get("benchmark") or {}
        return BenchmarkCleanSettings(
            clean_stale_outputs=bool(bench.get("clean_stale_outputs", False)),
            clean_stale_trace_cache=bool(
                bench.get("clean_stale_trace_cache", True)
            ),
        )
    except Exception:
        logger.debug("benchmark clean settings unavailable", exc_info=True)
        return BenchmarkCleanSettings()


def is_scenario_output_dir(path: Path) -> bool:
    """Return True when *path* looks like ``<scenario>/item*/`` output."""
    return path.is_dir() and any(path.glob("item*"))


def find_stale_scenario_dirs(
    output_dir: Path,
    active_scenario_ids: Iterable[str],
) -> list[Path]:
    """Scenario folders under *output_dir* that are absent from the experiment YAML."""
    active = set(active_scenario_ids)
    stale: list[Path] = []
    if not output_dir.is_dir():
        return stale
    for child in sorted(output_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in _RESERVED_OUTPUT_NAMES:
            continue
        if child.name in active:
            continue
        if is_scenario_output_dir(child):
            stale.append(child)
    return stale


def collect_trace_cache_refs(search_roots: Iterable[Path]) -> Counter[str]:
    """Count ``.run_ref`` pointers to trace-cache hashes under *search_roots*."""
    counts: Counter[str] = Counter()
    for root in search_roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            continue
        for ref_file in root.rglob(".run_ref"):
            try:
                run_hash = ref_file.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if run_hash:
                counts[run_hash] += 1
    return counts


def hashes_orphaned_after_removal(
    stale_dirs: Iterable[Path],
    search_roots: Iterable[Path],
) -> list[str]:
    """Trace-cache hashes referenced only under *stale_dirs*."""
    all_refs = collect_trace_cache_refs(search_roots)
    stale_refs: Counter[str] = Counter()
    for directory in stale_dirs:
        if not directory.is_dir():
            continue
        for ref_file in directory.rglob(".run_ref"):
            try:
                run_hash = ref_file.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if run_hash:
                stale_refs[run_hash] += 1
    orphaned: list[str] = []
    for run_hash, stale_count in stale_refs.items():
        if all_refs.get(run_hash, 0) == stale_count:
            orphaned.append(run_hash)
    return sorted(orphaned)


def clean_stale_scenarios(
    output_dir: Path,
    active_scenario_ids: Iterable[str],
    *,
    experiment_yaml: Path,
    trace_cache_dir: Optional[Path] = None,
    clean_trace_cache: bool = True,
    dry_run: bool = False,
    search_roots: Optional[Iterable[Path]] = None,
) -> StaleCleanReport:
    """Remove scenario output dirs no longer declared in the experiment YAML."""
    from mas.lab.benchmark.cli.common import _get_trace_cache_dir

    report = StaleCleanReport(dry_run=dry_run)
    report.stale_scenario_dirs = find_stale_scenario_dirs(
        output_dir, active_scenario_ids
    )
    if not report.stale_scenario_dirs:
        return report

    search = list(search_roots or [output_dir.parent])
    orphaned = (
        hashes_orphaned_after_removal(report.stale_scenario_dirs, search)
        if clean_trace_cache
        else []
    )

    if dry_run:
        report.removed_scenario_dirs = list(report.stale_scenario_dirs)
        report.removed_trace_cache_hashes = orphaned
        return report

    for sc_dir in report.stale_scenario_dirs:
        shutil.rmtree(sc_dir)
        report.removed_scenario_dirs.append(sc_dir)

    csv_path = output_dir / "results.csv"
    if csv_path.is_file():
        csv_path.unlink()

    if clean_trace_cache and orphaned:
        tc_root = _get_trace_cache_dir(trace_cache_dir)
        for run_hash in orphaned:
            tc_entry = tc_root / run_hash
            if tc_entry.is_dir():
                report.removed_trace_cache_hashes.append(run_hash)
                shutil.rmtree(tc_entry)

    return report


def format_clean_command(
    experiment_yaml: Path,
    stale_dirs: list[Path],
    *,
    output_dir: Path | None = None,
) -> str:
    """Suggest a ``mas-lab benchmark clean`` invocation for *stale_dirs*."""
    parts = ["mas-lab", "benchmark", "clean", str(experiment_yaml)]
    for sc_dir in stale_dirs:
        parts.extend(["--scenario", sc_dir.name])
    if output_dir is not None:
        parts.extend(["-o", str(output_dir)])
    return " ".join(parts)


def maybe_handle_stale_outputs(
    output_dir: Path,
    active_scenario_ids: list[str],
    experiment_yaml: Path,
    *,
    clean_stale: bool | None = None,
    dry_run: bool = False,
    trace_cache_dir: Optional[Path] = None,
) -> StaleCleanReport | None:
    """Warn about or remove stale scenario folders before a benchmark run."""
    stale_dirs = find_stale_scenario_dirs(output_dir, active_scenario_ids)
    if not stale_dirs:
        return None

    settings = load_benchmark_clean_settings(experiment_yaml.parent)
    auto_clean = (
        clean_stale
        if clean_stale is not None
        else settings.clean_stale_outputs
    )
    clean_trace_cache = settings.clean_stale_trace_cache

    names = ", ".join(d.name for d in stale_dirs)
    if dry_run:
        report = clean_stale_scenarios(
            output_dir,
            active_scenario_ids,
            experiment_yaml=experiment_yaml,
            trace_cache_dir=trace_cache_dir,
            clean_trace_cache=clean_trace_cache,
            dry_run=True,
        )
        print(
            f"\nStale benchmark output ({len(stale_dirs)} scenario dir(s)): {names}"
        )
        print(f"  Would remove: {', '.join(d.name for d in stale_dirs)}")
        if report.removed_trace_cache_hashes:
            print(
                "  Would prune trace-cache entries: "
                + ", ".join(report.removed_trace_cache_hashes)
            )
        print(
            "\nRe-run without --dry-run and with --clean-stale to remove automatically, "
            "or run:"
        )
        print(f"  {format_clean_command(experiment_yaml, stale_dirs, output_dir=output_dir)}")
        return report

    if auto_clean:
        report = clean_stale_scenarios(
            output_dir,
            active_scenario_ids,
            experiment_yaml=experiment_yaml,
            trace_cache_dir=trace_cache_dir,
            clean_trace_cache=clean_trace_cache,
            dry_run=False,
            search_roots=[output_dir.parent],
        )
        print(
            f"Removed stale benchmark output ({len(report.removed_scenario_dirs)} "
            f"scenario dir(s)): {names}"
        )
        if report.removed_trace_cache_hashes:
            print(
                "Pruned unreferenced trace-cache entries: "
                + ", ".join(report.removed_trace_cache_hashes)
            )
        return report

    print(
        f"\n⚠ Stale benchmark output detected ({len(stale_dirs)} scenario dir(s) "
        f"not in experiment YAML): {names}"
    )
    print("  Remove manually, re-run with --clean-stale, or enable in config.yaml:")
    print("    mas_lab.benchmark.clean_stale_outputs: true")
    print(f"  {format_clean_command(experiment_yaml, stale_dirs, output_dir=output_dir)}")
    return StaleCleanReport(stale_scenario_dirs=stale_dirs)
