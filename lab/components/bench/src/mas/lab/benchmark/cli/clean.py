#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark cache clean command."""

import logging
from pathlib import Path

from mas.lab.benchmark.cli.common import _get_trace_cache_dir

logger = logging.getLogger(__name__)

def clean_command(args) -> int:
    """Delete cached runs for selected scenarios so they are re-executed on the next run.

    What gets deleted
    -----------------
    For each matched scenario directory under ``<output_dir>/<scenario>/``:

    * All ``item*/r*`` run directories (``run_info.json``, ``metrics.json``,
      symlinked ``traces/``, ``.run_ref``) are removed.
    * The corresponding global trace-cache entry (``trace_cache()/<hash>/``)
      is removed, unless ``--keep-traces`` is given.

    After the run dirs are gone, the next ``mas-lab benchmark run`` will
    re-execute those scenarios from scratch and overwrite ``results.csv``.

    Examples
    --------
    # Wipe only the ToT scenario from the design-patterns experiment
    mas-lab benchmark clean labs/design-space.lab/01-design-patterns/experiment.yaml \\
        --scenario pattern-tree-of-thoughts

    # Dry-run: see what would be removed without touching anything
    mas-lab benchmark clean labs/design-space.lab/01-design-patterns/experiment.yaml \\
        --scenario pattern-tree-of-thoughts --dry-run

    # Wipe ALL scenarios (full reset, keeps experiment dir)
    mas-lab benchmark clean labs/design-space.lab/01-design-patterns/experiment.yaml
    """
    import shutil

    experiment_yaml = Path(args.experiment_yaml).resolve()
    dry_run: bool = args.dry_run
    keep_traces: bool = args.keep_traces
    scenario_filter: list[str] | None = args.scenarios  # None → clean all

    # ------------------------------------------------------------------
    # Resolve experiment output directory
    # ------------------------------------------------------------------
    output_dir_override: Path | None = getattr(args, "output_dir", None)

    if output_dir_override is not None:
        output_dir = Path(output_dir_override).expanduser().resolve()
    elif str(experiment_yaml) == str(Path("-").resolve()):
        print("✗ EXPERIMENT_YAML is '-' but --output-dir was not provided.")
        return 1
    else:
        try:
            from mas.lab.lab.config import MASExperimentConfig
            exp = MASExperimentConfig.from_yaml(experiment_yaml)
            output_dir = exp.output_dir
        except Exception as exc:
            print(f"✗ Cannot load experiment YAML: {exc}")
            return 1

    if not output_dir.exists():
        print(f"Output directory does not exist — nothing to clean: {output_dir}")
        return 0

    # ------------------------------------------------------------------
    # Enumerate scenario dirs to clean
    # ------------------------------------------------------------------
    if scenario_filter:
        scenario_dirs = []
        for sc_id in scenario_filter:
            d = output_dir / sc_id
            if not d.exists():
                print(f"  ⚠ Scenario dir not found (already clean?): {d}")
            else:
                scenario_dirs.append(d)
    else:
        # All subdirectories that look like scenario dirs (contain item* children)
        scenario_dirs = [
            d for d in sorted(output_dir.iterdir())
            if d.is_dir() and any(d.glob("item*"))
        ]

    if not scenario_dirs:
        print("Nothing to clean.")
        return 0

    tc_root = _get_trace_cache_dir()
    search_roots = [output_dir.parent]

    total_runs = 0
    total_tc_entries = 0
    pending_removals: list[tuple[Path, str | None]] = []

    for sc_dir in scenario_dirs:
        print(f"\nScenario: {sc_dir.name}  ({sc_dir})")
        run_dirs = sorted(sc_dir.glob("item*/r*"))

        for run_dir in run_dirs:
            if not run_dir.is_dir():
                continue
            total_runs += 1

            tc_hash: str | None = None
            run_ref = run_dir / ".run_ref"
            if run_ref.exists():
                tc_hash = run_ref.read_text().strip()

            print(f"  {run_dir.relative_to(output_dir)}  hash={tc_hash or '(none)'}")
            pending_removals.append((run_dir, tc_hash))

            if not dry_run:
                shutil.rmtree(run_dir)

        if not dry_run:
            for item_dir in sorted(sc_dir.glob("item*")):
                if item_dir.is_dir() and not any(item_dir.iterdir()):
                    item_dir.rmdir()

    if not keep_traces:
        from mas.lab.benchmark.stale_cleanup import (
            collect_trace_cache_refs,
            hashes_orphaned_after_removal,
        )

        removed_dirs = [run_dir for run_dir, _ in pending_removals]
        if dry_run:
            remaining = collect_trace_cache_refs(search_roots)
            stale_refs: dict[str, int] = {}
            for _run_dir, tc_hash in pending_removals:
                if tc_hash:
                    stale_refs[tc_hash] = stale_refs.get(tc_hash, 0) + 1
            for tc_hash, stale_count in stale_refs.items():
                if remaining.get(tc_hash, 0) == stale_count:
                    tc_entry = tc_root / tc_hash
                    if tc_entry.exists():
                        total_tc_entries += 1
                        print(f"    trace-cache: {tc_entry}")
        else:
            run_dirs_to_remove = removed_dirs
            for tc_hash in hashes_orphaned_after_removal(
                run_dirs_to_remove, search_roots
            ):
                tc_entry = tc_root / tc_hash
                if tc_entry.exists():
                    total_tc_entries += 1
                    print(f"    trace-cache: {tc_entry}")
                    shutil.rmtree(tc_entry)

    # results.csv is stale once runs are gone — remove it so it gets regenerated
    csv_path = output_dir / "results.csv"
    if csv_path.exists() and not dry_run and not keep_traces:
        print(f"\nRemoving stale results.csv: {csv_path}")
        csv_path.unlink()

    action = "Would delete" if dry_run else "Deleted"
    print(
        f"\n{'[DRY-RUN] ' if dry_run else ''}"
        f"{action} {total_runs} run dir(s) across {len(scenario_dirs)} scenario(s)"
        + (f", {total_tc_entries} trace-cache entr(ies)" if not keep_traces else "")
    )
    return 0


