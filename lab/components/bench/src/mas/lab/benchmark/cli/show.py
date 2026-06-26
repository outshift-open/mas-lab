#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark show and lab-tree commands."""

import logging
from pathlib import Path

from mas.lab.benchmark.run_manager import BenchmarkRunManager
from mas.lab.benchmark.reporting import print_benchmark_summary

from mas.lab.benchmark.cli.common import _get_trace_cache_dir, _resolve_run_manager_dir

logger = logging.getLogger(__name__)

from mas.lab.benchmark.cli.tree import _PIPELINE_ARTIFACT_SCHEMA, _render_exp_tree, _render_pipeline_dag

# ---------------------------------------------------------------------------
# show_command helpers
# ---------------------------------------------------------------------------

def _show_plots(metadata, run_dir: Path) -> int:
    """List plot files for a benchmark run."""
    plots_dir = Path(metadata.plots_dir) if metadata.plots_dir else run_dir / "plots"
    if not plots_dir.exists():
        print(f"No plots directory found at: {plots_dir}")
        print("Run the benchmark first, or generate plots with:")
        print(f"  mas-lab benchmark pipeline run <pipeline.yaml>")
        return 1

    files = sorted(plots_dir.rglob("*"))
    files = [f for f in files if f.is_file()]
    if not files:
        print(f"Plots directory is empty: {plots_dir}")
        return 1

    print(f"Plots in {plots_dir}:")
    for f in files:
        print(f"  {f}")
    return 0


def _show_events_traces(run_dir: Path) -> int:
    """List per-run event trace files (traces/events.jsonl)."""
    runs_dir = run_dir / "runs"
    if not runs_dir.exists():
        print(f"No runs directory found at: {runs_dir}")
        return 1

    traces = sorted(runs_dir.glob("*/traces/events.jsonl"))
    if not traces:
        print(f"No event traces found under: {runs_dir}")
        return 1

    print(f"Event traces ({len(traces)} run(s)):")
    for t in traces:
        rel = t.relative_to(run_dir)
        size = t.stat().st_size
        print(f"  {rel}  ({size:,} bytes)")
    return 0


def _show_otel_traces(run_dir: Path) -> int:
    """List OTel span files written by the Docker collector."""
    otel_dir = run_dir / "otel"
    if not otel_dir.exists():
        print(f"No OTel traces directory found at: {otel_dir}")
        print("OTel spans are only collected when the flavour uses otel_extended backend.")
        return 1

    files = sorted(otel_dir.rglob("*"))
    files = [f for f in files if f.is_file()]
    if not files:
        print(f"OTel directory is empty: {otel_dir}")
        return 1

    print(f"OTel traces in {otel_dir}:")
    for f in files:
        size = f.stat().st_size
        print(f"  {f}  ({size:,} bytes)")
    return 0


def show_command(args) -> int:
    """Show details of a benchmark run."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )

    # Handle "last" / "latest" as alias for most-recent run
    if args.benchmark_id in ("last", "latest"):
        result = run_manager.get_last_run()
        if not result:
            logger.error("No benchmark runs found.")
            return 1
    else:
        result = run_manager.get_run(args.benchmark_id)
        if not result:
            logger.error(f"Benchmark run not found: {args.benchmark_id}")
            return 1

    metadata, run_dir = result

    # Dispatch on 'what' (default: info)
    what = getattr(args, "what", "info") or "info"

    if what == "plots":
        return _show_plots(metadata, run_dir)

    if what == "events-trace":
        return _show_events_traces(run_dir)

    if what == "otel-traces":
        return _show_otel_traces(run_dir)

    # -- default: info --

    # Get verbose flag (default: False)
    verbose = getattr(args, "verbose", False)

    # Resolve trace-cache dir (CLI > env var > default)
    trace_cache_dir = _get_trace_cache_dir(explicit=getattr(args, "trace_cache_dir", None))

    # Print details (concise by default, full with --verbose)
    print(run_manager.format_run_details(metadata, run_dir, verbose=verbose,
                                         trace_cache_root=trace_cache_dir))
    
    # Only show detailed info in verbose mode
    if verbose:
        # Show hierarchy
        if metadata.n_scenarios:
            n_items = metadata.n_tests // max(metadata.n_scenarios, 1)
            print()
            print("Hierarchy:")
            print(f"  Scenarios:  {metadata.n_scenarios}")
            print(f"  Tests:      {metadata.n_tests} (scenario × item)")
            print(f"  Runs:       {metadata.n_runs_per_test} per test = {metadata.total_scenarios} total")
            print(f"  Formula:    {metadata.n_scenarios} × {n_items} × {metadata.n_runs_per_test} = {metadata.total_scenarios}")
        
        # Show state if available
        state = run_manager.load_state(run_dir)
        if state:
            print()
            print("State:")
            print(f"  Pending:    {state.pending_count}")
            print(f"  Completed:  {state.completed_count}")
            print(f"  Successful: {state.success_count}")
            print(f"  Failed:     {state.failed_count}")
        
        # Show results summary if available
        results_path = run_dir / "results.csv"
        if results_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(results_path)
                if len(df) > 0:
                    print()
                    print_benchmark_summary(
                        df,
                        n_scenarios=metadata.n_scenarios or df["scenario"].nunique(),
                        n_tests=metadata.n_tests or df.groupby(["scenario", "item_id"]).ngroups,
                        n_runs_per_test=metadata.n_runs_per_test or df["run_id"].nunique(),
                    )
            except Exception as e:
                logger.debug(f"Could not load results: {e}")
    
    # Show resume hint if interrupted (all modes)
    if run_manager.can_resume(metadata.benchmark_id):
        print()
        print(f"⏸️  This run can be resumed with:")
        print(f"   mas-lab benchmark run <yaml> --benchmark-id {metadata.short_id} --resume")
    
    return 0


# ---------------------------------------------------------------------------
# show_artifact_by_id_command — look up a single artifact by its short hash
# ---------------------------------------------------------------------------

def show_artifact_by_id_command(args) -> int:
    """Find an artifact anywhere in the lab tree by its 8-char SHA-256 prefix."""
    import hashlib as _hlib

    art_id: str = args.artifact_id.lower()
    search_root = Path(getattr(args, "search_root", ".")).resolve()

    # Collect experiment YAMLs (same logic as show_lab_tree_command)
    exp_yamls: list = []
    direct = search_root / "experiment.yaml"
    if direct.exists():
        exp_yamls = [direct]
    else:
        exp_yamls = sorted(search_root.glob("*/experiment.yaml"))
    if not exp_yamls:
        logger.error(f"No experiment.yaml found under {search_root}")
        return 1

    from mas.lab.lab.config import MASExperimentConfig
    from mas.lab.artifacts import classify_file as _classify_file

    def _data_dir_for(exp_yaml: "Path") -> "Path | None":
        try:
            exp = MASExperimentConfig.from_yaml(exp_yaml)
        except Exception:
            return None
        dd = getattr(exp, "output_dir", None)
        if dd and dd.exists():
            csv = dd / "results.csv"
            if csv.exists() and csv.stat().st_size > 150:
                return dd
        # legacy fallback
        if exp.name:
            try:
                from mas.lab import paths as _paths
                fb = _paths.labs_root() / exp.name
                if fb.exists():
                    return fb
            except Exception:
                logger.debug('suppressed', exc_info=True)
        return dd if (dd and dd.exists()) else None

    for exp_yaml in exp_yamls:
        dd = _data_dir_for(exp_yaml)
        if dd is None:
            continue
        for fpath in sorted(dd.rglob("*")):
            if not fpath.is_file():
                continue
            try:
                fhash = _hlib.sha256(fpath.read_bytes()).hexdigest()[:8]
            except Exception:
                continue
            if fhash != art_id:
                continue
            # Found — print details
            ft = _classify_file(fpath)
            try:
                display_path = "~/" + str(fpath.relative_to(Path.home()))
            except ValueError:
                display_path = str(fpath)
            size_kb = fpath.stat().st_size / 1024
            exp_label = exp_yaml.parent.name
            try:
                _exp = MASExperimentConfig.from_yaml(exp_yaml)
                exp_name = _exp.name
            except Exception:
                exp_name = "?"
            print(f"artifact  {art_id}")
            print(f"  type:  [{ft.abbrev}] {ft.label}")
            print(f"  file:  {fpath.name}")
            print(f"  path:  {display_path}")
            print(f"  size:  {size_kb:.1f} KB")
            print(f"  exp:   {exp_label}  [{exp_name}]")
            if ft.description:
                print(f"  desc:  {ft.description}")
            if ft.produced_by:
                print(f"  from:  {', '.join(ft.produced_by)}")
            return 0

    logger.error(f"No artifact found with id '{art_id}' under {search_root}")
    return 1


# ---------------------------------------------------------------------------
# show_lab_tree_command — recursive lab/experiment tree view
# ---------------------------------------------------------------------------

def show_lab_tree_command(args) -> int:
    """Show a lab or experiment directory as a hierarchical tree.

    Verbosity levels:
      0 (default) — structure only: scenarios + item/run counts
      1 (-v)       — + final output artifacts (results.csv, figures)
      2 (-vv)      — + intermediate artifacts (.cache fingerprints, metrics.json)
      3 (-vvv)     — + pipeline DAG with artifact lineage and provenance
    """
    target = Path(args.target).resolve()
    verbose: int = getattr(args, "verbose", 0)
    scenario_filter: "str | None" = getattr(args, "scenario", None)
    item_filter: "str | None" = getattr(args, "item", None)
    run_filter: "int | None" = getattr(args, "run_idx", None)
    artifact_type_filter: "str | None" = getattr(args, "artifact_type", None)
    artifacts_only: bool = getattr(args, "artifacts_only", False)
    # depth controls how many levels of the tree are expanded.
    # Map named levels → integer for easy comparison:
    #   exp=1  scenario=2 (default)  item=3  run=4
    _DEPTH_MAP = {"exp": 1, "experiment": 1, "scenario": 2, "item": 3, "run": 4}
    depth_str: "str | None" = getattr(args, "depth", None)
    depth_int: int = _DEPTH_MAP.get(depth_str or "scenario", 2)
    # artifacts_only implies at least -v
    if artifacts_only and verbose < 1:
        verbose = 1

    # Collect experiment YAML files under target
    exp_yamls: list = []
    if target.is_dir():
        direct = target / "experiment.yaml"
        if direct.exists():
            exp_yamls = [direct]
        else:
            exp_yamls = sorted(target.glob("*/experiment.yaml"))
    elif target.suffix == ".yaml" and target.exists():
        exp_yamls = [target]

    if not exp_yamls:
        logger.error(f"No experiment.yaml found under {target}")
        return 1

    # Display root label
    _cwd = Path.cwd()
    try:
        display_root = str(target.relative_to(_cwd))
    except ValueError:
        display_root = str(target)

    multi = len(exp_yamls) > 1
    if multi:
        print(f"{display_root}/")

    for i, exp_yaml in enumerate(exp_yamls):
        is_last = i == len(exp_yamls) - 1
        _render_exp_tree(
            exp_yaml=exp_yaml,
            verbose=verbose,
            depth=depth_int,
            scenario_filter=scenario_filter,
            item_filter=item_filter,
            run_filter=run_filter,
            artifact_type_filter=artifact_type_filter,
            artifacts_only=artifacts_only,
            prefix="└── " if (multi and is_last) else ("├── " if multi else ""),
            child_prefix="    " if (multi and is_last) else ("│   " if multi else ""),
        )

    return 0


