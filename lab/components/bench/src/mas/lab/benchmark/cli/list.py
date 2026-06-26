#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark list command."""

import logging
from pathlib import Path

from mas.lab.benchmark.metadata import BenchmarkStatus
from mas.lab.benchmark.run_manager import BenchmarkRunManager
from mas.lab.utils.output_formatter import format_table

from mas.lab.benchmark.cli.common import _resolve_run_manager_dir

logger = logging.getLogger(__name__)

def list_command(args) -> int:
    """List all benchmark runs."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )
    
    # Get filter
    status_filter = None
    if args.status:
        try:
            status_filter = BenchmarkStatus(args.status)
        except ValueError:
            logger.error(f"Invalid status: {args.status}")
            logger.info(f"Valid statuses: {', '.join(s.value for s in BenchmarkStatus)}")
            return 1
    
    # List runs
    runs = run_manager.list_runs(status_filter=status_filter, limit=args.limit)

    # Filter by experiment YAML path
    experiment_filter: Path | None = getattr(args, "experiment", None)
    if experiment_filter is not None:
        _exp_resolved = str(experiment_filter.resolve())
        runs = [r for r in runs if r.experiment_yaml_path == _exp_resolved]
    
    if not runs:
        print("No benchmark runs found")
        return 0
    
    # Get output format
    output_format = getattr(args, "format", "simple")
    
    # Convert runs to dict format
    status_emoji = {
        BenchmarkStatus.RUNNING: "🔄",
        BenchmarkStatus.COMPLETED: "✅",
        BenchmarkStatus.FAILED: "❌",
        BenchmarkStatus.INTERRUPTED: "⏸️",
    }
    
    data = []
    for run_info in runs:
        emoji = status_emoji.get(run_info.status, "❓")
        # Build hierarchy string: "12 × 60 × 3 = 180"
        if run_info.n_scenarios:
            n_items = run_info.n_tests // max(run_info.n_scenarios, 1)
            hierarchy = f"{run_info.n_scenarios}×{n_items}×{run_info.n_runs_per_test}"
        else:
            hierarchy = "-"
        # Use name if present, otherwise experiment name
        display_name = run_info.name if run_info.name else run_info.experiment_name[:30]
        # Format tags
        tags_str = ", ".join(run_info.tags) if run_info.tags else "-"
        data.append({
            "status_icon": emoji,
            "id": run_info.short_id,
            "timestamp": run_info.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "experiment": display_name[:30],
            "tags": tags_str[:20],  # Truncate long tag lists
            "status": run_info.status.value,
            "scenarios": str(run_info.n_scenarios) if run_info.n_scenarios else "-",
            "tests": str(run_info.n_tests) if run_info.n_tests else "-",
            "runs": f"{run_info.completed_scenarios}/{run_info.total_scenarios}",
        })
    
    # Format output
    columns = ["status_icon", "id", "timestamp", "experiment", "tags", "status", "scenarios", "tests", "runs"]
    headers = {
        "status_icon": "",
        "id": "ID",
        "timestamp": "Timestamp",
        "experiment": "Experiment",
        "tags": "Tags",
        "status": "Status",
        "scenarios": "Scenarios",
        "tests": "Tests",
        "runs": "Runs",
    }
    
    output = format_table(data, format=output_format, columns=columns, headers=headers)
    print(output)
    
    # Add summary footer (only for table formats)
    if output_format in ["simple", "plain", "grid", "pipe", "markdown"]:
        print(f"\nTotal: {len(runs)} runs")
        if status_filter:
            print(f"Filter: status={status_filter.value}")
    
    return 0


