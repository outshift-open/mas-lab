#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark result reporting and post-processing."""

import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

def print_benchmark_summary(df, n_scenarios: int, n_tests: int, n_runs_per_test: int):
    """Print 3-level benchmark statistics: scenario, test, run.
    
    Args:
        df: DataFrame with columns: scenario, item_id, run_id, success, latency_ms, tokens
        n_scenarios: Number of unique scenarios (scenario level)
        n_tests: Number of unique (scenario × item) pairs (test level)
        n_runs_per_test: Number of runs per test (run level)
    """
    import numpy as np
    
    total_runs = len(df)
    total_success = df["success"].sum()
    total_fail = total_runs - total_success
    
    print()
    print("=" * 80)
    print("  BENCHMARK RESULTS")
    print("=" * 80)
    print(f"  {n_scenarios} scenarios × {n_tests // max(n_scenarios, 1)} items × {n_runs_per_test} runs = {total_runs} executions")
    print(f"  Success: {total_success}/{total_runs} ({100*total_success/max(total_runs,1):.0f}%)   Failed: {total_fail}")
    print()
    
    # ── Level 1: Scenario (per variant) ─────────────────────────────────
    print("─" * 80)
    print("  SCENARIO LEVEL")
    print("─" * 80)
    
    scenario_stats = df.groupby("scenario").agg(
        runs=("success", "count"),
        successes=("success", "sum"),
        latency_mean=("latency_ms", "mean"),
        latency_std=("latency_ms", "std"),
        tokens_mean=("tokens", "mean"),
    ).reset_index()
    scenario_stats["success_rate"] = (100 * scenario_stats["successes"] / scenario_stats["runs"])
    scenario_stats = scenario_stats.sort_values("scenario")
    
    # Print header
    print(f"  {'Scenario':<28s} {'Runs':>5s} {'Pass':>5s} {'Rate':>6s} {'Latency (ms)':>14s} {'Tokens':>8s}")
    print(f"  {'─'*28} {'─'*5} {'─'*5} {'─'*6} {'─'*14} {'─'*8}")
    
    for _, row in scenario_stats.iterrows():
        std_str = f"±{row['latency_std']:.0f}" if not np.isnan(row['latency_std']) else ""
        print(
            f"  {row['scenario']:<28s} {int(row['runs']):>5d} {int(row['successes']):>5d}"
            f" {row['success_rate']:>5.0f}%"
            f" {row['latency_mean']:>7.0f} {std_str:>6s}"
            f" {row['tokens_mean']:>8.0f}"
        )
    print()
    
    # ── Level 2: Test (per variant × item) ──────────────────────────────
    print("─" * 80)
    print("  TEST LEVEL (per scenario × item)")
    print("─" * 80)
    
    test_stats = df.groupby(["scenario", "item_id"]).agg(
        runs=("success", "count"),
        successes=("success", "sum"),
        latency_mean=("latency_ms", "mean"),
        latency_std=("latency_ms", "std"),
    ).reset_index()
    test_stats["success_rate"] = (100 * test_stats["successes"] / test_stats["runs"])
    
    # Summary per scenario (how many tests passed vs failed)
    test_stats["all_passed"] = test_stats["successes"] == test_stats["runs"]
    
    test_summary = test_stats.groupby("scenario").agg(
        tests=("item_id", "count"),
        tests_all_pass=("all_passed", "sum"),
        latency_cv=("latency_std", "mean"),  # mean of per-test std = run consistency
    ).reset_index()
    test_summary = test_summary.sort_values("scenario")
    
    print(f"  {'Scenario':<28s} {'Tests':>6s} {'All-pass':>9s} {'Consistency':>12s}")
    print(f"  {'─'*28} {'─'*6} {'─'*9} {'─'*12}")
    
    for _, row in test_summary.iterrows():
        cv_str = f"±{row['latency_cv']:.0f}ms" if not np.isnan(row['latency_cv']) else "n/a"
        print(
            f"  {row['scenario']:<28s} {int(row['tests']):>6d}"
            f" {int(row['tests_all_pass']):>4d}/{int(row['tests']):>d}"
            f" {cv_str:>12s}"
        )
    print()
    
    # ── Level 3: Run (individual executions) ────────────────────────────
    print("─" * 80)
    print("  RUN LEVEL (individual executions)")
    print("─" * 80)
    
    run_stats = df.groupby("run_id").agg(
        count=("success", "count"),
        successes=("success", "sum"),
        latency_mean=("latency_ms", "mean"),
    ).reset_index()
    run_stats["success_rate"] = (100 * run_stats["successes"] / run_stats["count"])
    
    print(f"  {'Run':>5s} {'Executions':>11s} {'Pass':>5s} {'Rate':>6s} {'Avg latency':>12s}")
    print(f"  {'─'*5} {'─'*11} {'─'*5} {'─'*6} {'─'*12}")
    
    for _, row in run_stats.iterrows():
        print(
            f"  {int(row['run_id']):>5d} {int(row['count']):>11d}"
            f" {int(row['successes']):>5d} {row['success_rate']:>5.0f}%"
            f" {row['latency_mean']:>9.0f} ms"
        )
    
    print()
    print("=" * 80)
    print()


def generate_plots(df: "pd.DataFrame", experiment, plots_dir: Path, logger):
    """Generate all plots for a benchmark."""
    from plotnine import (
        ggplot, aes,
        geom_bar, geom_boxplot, geom_point, geom_text, geom_errorbar, geom_blank,
        labs, theme_minimal, theme, element_text,
        scale_y_continuous, coord_cartesian
    )
    import numpy as np

    plots_dir.mkdir(parents=True, exist_ok=True)
    exec_spec = getattr(experiment, "execution", None)
    if isinstance(exec_spec, dict):
        show_ci = exec_spec.get("show_confidence_interval", True)
    else:
        show_ci = getattr(exec_spec, "show_confidence_interval", True)

    for plot_spec in experiment.plots:
        plot_name = plot_spec.name
        logger.info(f"Generating plot: {plot_name}")

        try:
            if plot_name == "latency_by_scenario":
                scenario_stats_plot = df.groupby("scenario", as_index=False).agg({
                    "latency_ms": ["mean", "std", "count"]
                })
                scenario_stats_plot.columns = ["scenario", "mean", "std", "count"]
                scenario_stats_plot["ci"] = 1.96 * scenario_stats_plot["std"] / np.sqrt(scenario_stats_plot["count"])
                scenario_stats_plot["ymin"] = scenario_stats_plot["mean"] - scenario_stats_plot["ci"]
                scenario_stats_plot["ymax"] = scenario_stats_plot["mean"] + scenario_stats_plot["ci"]

                plot = (
                    ggplot(scenario_stats_plot, aes(x='scenario', y='mean')) +
                    geom_bar(stat='identity', fill='steelblue', alpha=0.7) +
                    (geom_errorbar(aes(ymin='ymin', ymax='ymax'), width=0.3) if show_ci else geom_blank()) +
                    labs(title="Latency by Scenario",
                         x="Scenario", y="Latency (ms)") +
                    theme_minimal() +
                    theme(axis_text_x=element_text(angle=45, hjust=1))
                )

            elif plot_name == "success_by_scenario":
                scenario_success = df.groupby("scenario", as_index=False).agg({
                    "success": lambda x: (x.astype(int).mean() * 100)
                })
                scenario_success.columns = ["scenario", "success_rate"]

                plot = (
                    ggplot(scenario_success, aes(x='scenario', y='success_rate')) +
                    geom_bar(stat='identity', fill='forestgreen', alpha=0.7) +
                    coord_cartesian(ylim=(0, 105)) +
                    labs(title="Success Rate by Scenario",
                         x="Scenario", y="Success Rate (%)") +
                    theme_minimal() +
                    theme(axis_text_x=element_text(angle=45, hjust=1))
                )

            elif plot_name == "pattern_comparison":
                df_plot = df.copy()
                df_plot["pattern_type"] = df_plot["scenario"].str.split("_").str[0]

                plot = (
                    ggplot(df_plot, aes(x='pattern_type', y='latency_ms')) +
                    geom_boxplot(fill='lightblue', alpha=0.7) +
                    labs(title="Latency Distribution by Pattern Type",
                         x="Pattern Type", y="Latency (ms)") +
                    theme_minimal()
                )

            elif plot_name == "pareto_frontier":
                scenario_stats_pareto = df.groupby("scenario", as_index=False).agg({
                    "latency_ms": "mean",
                    "success": lambda x: x.astype(int).mean() * 100
                })
                scenario_stats_pareto.columns = ["scenario", "latency_ms", "success_rate"]

                plot = (
                    ggplot(scenario_stats_pareto, aes(x='latency_ms', y='success_rate')) +
                    geom_point(size=3, alpha=0.6, color='steelblue') +
                    geom_text(aes(label='scenario'), size=8, alpha=0.7,
                             nudge_x=0.05, nudge_y=0.5) +
                    labs(title="Pareto Frontier: Latency vs Success",
                         x="Latency (ms)", y="Success Rate (%)") +
                    theme_minimal()
                )
            else:
                logger.warning(f"  Unknown plot type: {plot_name}")
                continue

            plot_path = plots_dir / f"{plot_name}.svg"
            plot.save(plot_path, format='svg', width=12, height=6, dpi=150, verbose=False)
            logger.info(f"  Saved: {plot_path}")

        except Exception as e:
            logger.error(f"  Failed to generate {plot_name}: {e}")
            import traceback
            traceback.print_exc()

