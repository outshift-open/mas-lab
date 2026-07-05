#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover benchmark run directories under experiment output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SKIP_TOP = frozenset({"data", "results", "logs", ".cache", "shared"})
_SKIP_PREFIXES = (
    "normalize-",
    "compare-",
    "verify-",
    "validate-",
    "events-",
    "plot-",
)


@dataclass(frozen=True)
class BenchmarkRunRef:
    """One benchmark run: ``{output_dir}/{scenario}/{test}/{run}/``."""

    scenario: str
    test: str
    run: str
    path: Path


def _is_scenario_dir(path: Path) -> bool:
    if not path.is_dir() or path.name.startswith("."):
        return False
    if path.name in _SKIP_TOP:
        return False
    if any(path.name.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return False
    return any(child.is_dir() and child.name.startswith("item") for child in path.iterdir())


def discover_benchmark_runs(
    output_dir: Path,
    *,
    scenario: str | None = None,
) -> list[BenchmarkRunRef]:
    """List run folders under ``{scenario}/item*/r*/``."""
    base = Path(output_dir)
    if not base.is_dir():
        return []

    scenario_dirs: list[Path]
    if scenario:
        candidate = base / scenario
        scenario_dirs = [candidate] if candidate.is_dir() else []
    else:
        scenario_dirs = sorted(p for p in base.iterdir() if _is_scenario_dir(p))

    runs: list[BenchmarkRunRef] = []
    for scenario_dir in scenario_dirs:
        for item_dir in sorted(scenario_dir.iterdir()):
            if not item_dir.is_dir() or not item_dir.name.startswith("item"):
                continue
            for run_dir in sorted(item_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("r"):
                    continue
                runs.append(
                    BenchmarkRunRef(
                        scenario=scenario_dir.name,
                        test=item_dir.name,
                        run=run_dir.name,
                        path=run_dir.resolve(),
                    )
                )
    return runs
