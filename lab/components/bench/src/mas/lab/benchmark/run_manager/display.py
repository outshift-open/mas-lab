#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""Benchmark run display formatting."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from mas.lab.benchmark.metadata import BenchmarkMetadata, BenchmarkStatus
from mas.lab.benchmark.run_manager.models import BenchmarkRunInfo
from mas.lab.benchmark.run_manager.stats import count_cached_runs, read_quality_stats


def format_run_summary(run_info: BenchmarkRunInfo) -> str:
    """Format a run summary for display."""
    status_emoji = {
        BenchmarkStatus.RUNNING: "🔄",
        BenchmarkStatus.COMPLETED: "✅",
        BenchmarkStatus.FAILED: "❌",
        BenchmarkStatus.INTERRUPTED: "⏸️",
    }

    emoji = status_emoji.get(run_info.status, "❓")
    timestamp_str = run_info.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    completion = f"{run_info.completion_rate * 100:.1f}%"

    return (
        f"{emoji} {run_info.short_id} │ {timestamp_str} │ "
        f"{run_info.experiment_name[:30]:30s} │ "
        f"{run_info.status.value:11s} │ "
        f"{completion:6s} ({run_info.completed_scenarios}/{run_info.total_scenarios})"
    )


def format_run_details(
    metadata: BenchmarkMetadata,
    run_dir: Path,
    *,
    verbose: bool = False,
    trace_cache_root: Optional[Path] = None,
) -> str:
    """Format run information."""
    lines: list[str] = []

    if verbose:
        lines.append("=" * 80)
        lines.append(f"Benchmark Run: {metadata.benchmark_id}")
        lines.append("=" * 80)
        lines.append(f"Short ID:     {metadata.short_id}")
        lines.append(f"Timestamp:    {metadata.timestamp}")
        lines.append(f"Status:       {metadata.status.value}")
        if metadata.name:
            lines.append(f"Name:         {metadata.name}")
        if metadata.tags:
            lines.append(f"Tags:         {', '.join(metadata.tags)}")
        lines.append("")
        lines.append("Experiment:")
        lines.append(f"  Name:        {metadata.experiment_name}")
        lines.append(f"  Description: {metadata.experiment_description}")
        lines.append(f"  YAML:        {metadata.experiment_yaml_path}")
        lines.append("")
        lines.append("Progress:")
        lines.append(f"  Total:       {metadata.total_scenarios} scenarios")
        lines.append(
            f"  Completed:   {metadata.completed_scenarios} ({metadata.completion_rate * 100:.1f}%)"
        )
        lines.append(f"  Failed:      {metadata.failed_scenarios}")
        lines.append(f"  Success:     {metadata.success_rate * 100:.1f}%")

        _qstats = read_quality_stats(run_dir)
        if _qstats is not None and _qstats["total"] > 0:
            lines.append(
                f"  Quality:     {_qstats['ok']} ok  {_qstats.get('warn', 0)} warn  "
                f"{_qstats.get('error', 0)} error  (of {_qstats['total']} unique runs)"
            )

        lines.append("")
        lines.append("Resources:")
        lines.append(
            f"  Tokens:      {metadata.total_tokens:,} "
            f"({metadata.total_tokens_input:,} in, {metadata.total_tokens_output:,} out)"
        )
        lines.append(f"  Cost:        ${metadata.estimated_cost_usd:.4f}")

        if metadata.duration_seconds:
            duration = f"{metadata.duration_seconds:.1f}s"
            if metadata.duration_seconds > 60:
                minutes = int(metadata.duration_seconds // 60)
                seconds = int(metadata.duration_seconds % 60)
                duration = f"{minutes}m{seconds}s"
            lines.append(f"  Duration:    {duration}")

        lines.append("")
        lines.append("Paths:")
        lines.append(f"  Run dir:     {run_dir}")
        lines.append(f"  Results:     {metadata.results_file}")
        lines.append(f"  Plots:       {metadata.plots_dir}")
        lines.append("=" * 80)
    else:
        status_emoji = {
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "interrupted": "⏸️",
        }.get(metadata.status.value, "❓")

        lines.append(f"{status_emoji} {metadata.short_id} - {metadata.status.value}")
        if metadata.name:
            lines.append(f"Name: {metadata.name}")
        if metadata.tags:
            lines.append(f"Tags: {', '.join(metadata.tags)}")
        lines.append(f"Experiment: {metadata.experiment_name}")

        if metadata.n_scenarios and metadata.n_tests and metadata.n_runs_per_test:
            n_items = metadata.n_tests // max(metadata.n_scenarios, 1)
            lines.append(
                f"Hierarchy: {metadata.n_scenarios} scenarios × {n_items} items × "
                f"{metadata.n_runs_per_test} runs = {metadata.total_scenarios} total"
            )

        lines.append(
            f"Progress: {metadata.completed_scenarios}/{metadata.total_scenarios} "
            f"({metadata.completion_rate * 100:.0f}% success)"
        )

        _qstats = read_quality_stats(run_dir)
        if _qstats is not None and _qstats["total"] > 0:
            _qparts = [f"{_qstats['ok']} ok"]
            if _qstats.get("warn", 0):
                _qparts.append(f"{_qstats['warn']} warn")
            if _qstats.get("error", 0):
                _qparts.append(f"{_qstats['error']} error")
            lines.append(f"Quality: {', '.join(_qparts)}")

        cached, total = count_cached_runs(run_dir, trace_cache_root=trace_cache_root)
        if total > 0:
            pct = int(cached / total * 100)
            lines.append(f"Cache: {cached}/{total} runs available ({pct}%)")

        if metadata.status == BenchmarkStatus.RUNNING and metadata.eta_seconds:
            if metadata.eta_seconds < 60:
                eta_str = f"{metadata.eta_seconds:.0f}s"
            elif metadata.eta_seconds < 3600:
                minutes = int(metadata.eta_seconds // 60)
                eta_str = f"{minutes}m"
            else:
                hours = int(metadata.eta_seconds // 3600)
                minutes = int((metadata.eta_seconds % 3600) // 60)
                eta_str = f"{hours}h{minutes:02d}m"
            lines.append(f"ETA: {eta_str}")

        stats_parts: list[str] = []
        elapsed = metadata.elapsed_seconds if metadata.elapsed_seconds else metadata.duration_seconds
        throughput = metadata.throughput_scenarios_per_sec

        if elapsed and elapsed > 0:
            if elapsed < 60:
                duration_str = f"{elapsed:.0f}s"
            elif elapsed < 3600:
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                duration_str = f"{minutes}m{seconds}s"
            else:
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                duration_str = f"{hours}h{minutes:02d}m"

            if not throughput and metadata.completed_scenarios > 0:
                throughput = metadata.completed_scenarios / elapsed

            if throughput and throughput > 0:
                stats_parts.append(f"{duration_str} @ {throughput:.2f} scenarios/sec")
            else:
                stats_parts.append(duration_str)

        if metadata.total_tokens > 0:
            if metadata.total_tokens >= 1_000_000:
                tokens_str = f"{metadata.total_tokens / 1_000_000:.1f}M"
            elif metadata.total_tokens >= 1_000:
                tokens_str = f"{metadata.total_tokens / 1_000:.1f}K"
            else:
                tokens_str = str(metadata.total_tokens)
            stats_parts.append(f"{tokens_str} tokens")

            if metadata.completed_scenarios > 0:
                avg_tokens = metadata.total_tokens / metadata.completed_scenarios
                if avg_tokens >= 1_000:
                    avg_str = f"{avg_tokens / 1_000:.1f}K"
                else:
                    avg_str = f"{avg_tokens:.0f}"
                stats_parts.append(f"~{avg_str}/run")

        if metadata.estimated_cost_usd and metadata.estimated_cost_usd > 0:
            stats_parts.append(f"${metadata.estimated_cost_usd:.4f}")

        if stats_parts:
            lines.append(f"Statistics: {', '.join(stats_parts)}")

        if metadata.status == BenchmarkStatus.RUNNING and metadata.last_update_at:
            try:
                last_update = datetime.fromisoformat(metadata.last_update_at)
                age_seconds = (datetime.now() - last_update).total_seconds()
                if age_seconds < 60:
                    age_str = f"{age_seconds:.0f}s ago"
                elif age_seconds < 3600:
                    age_str = f"{age_seconds / 60:.0f}m ago"
                else:
                    age_str = f"{age_seconds / 3600:.1f}h ago"
                lines.append(f"Last update: {age_str}")
            except (ValueError, TypeError):
                logger.debug('suppressed', exc_info=True)

        lines.append(f"Output: {run_dir}")

    return "\n".join(lines)
