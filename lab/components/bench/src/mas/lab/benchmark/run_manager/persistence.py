#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark run state load/save — EnhancedBenchmarkState only."""

import logging
from pathlib import Path

from mas.lab.benchmark.state import EnhancedBenchmarkState

logger = logging.getLogger(__name__)


def load_state(run_dir: Path) -> EnhancedBenchmarkState | None:
    """Load :class:`EnhancedBenchmarkState` from *run_dir*.

    Returns ``None`` when ``state.json`` is absent.  Raises :class:`ValueError`
    when the file exists but is not a supported enhanced state format.
    """
    state_path = run_dir / "state.json"
    if not state_path.exists():
        return None

    try:
        return EnhancedBenchmarkState.from_json(state_path)
    except Exception as exc:
        raise ValueError(
            f"Unsupported benchmark state format at {state_path}. "
            "Only EnhancedBenchmarkState (current format) is supported. "
            "Re-run the benchmark or migrate state manually."
        ) from exc


def save_state(run_dir: Path, state: EnhancedBenchmarkState) -> None:
    """Persist *state* to ``state.json`` under *run_dir*."""
    state_path = run_dir / "state.json"
    state.to_json(state_path)
