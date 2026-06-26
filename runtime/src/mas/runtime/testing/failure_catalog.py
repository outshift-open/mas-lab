#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Re-export failure catalog runner from the ``failure_modes/`` artifact."""

from __future__ import annotations

import sys
from pathlib import Path

_RUNNER_DIR = Path(__file__).resolve().parents[5] / "failure_modes" / "runner"
if _RUNNER_DIR.is_dir() and str(_RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNNER_DIR))

from failure_catalog import (  # noqa: E402,F401
    ScenarioExpect,
    ScenarioResult,
    default_catalog_path,
    list_python_scenarios,
    load_failure_catalog,
    run_scenario,
)

__all__ = [
    "ScenarioExpect",
    "ScenarioResult",
    "default_catalog_path",
    "list_python_scenarios",
    "load_failure_catalog",
    "run_scenario",
]
