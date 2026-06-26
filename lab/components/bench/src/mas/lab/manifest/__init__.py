#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS manifest loading for bench runs (compose + agent resolution).

For versioned **experiment** and **pipeline** YAML, use ``mas.lab.manifests`` instead.

| Package | Purpose |
|---------|---------|
| ``mas.lab.manifest`` | MAS/agent YAML via ctl compose |
| ``mas.lab.manifests`` | Experiment/pipeline version shims |
"""

from mas.lab.manifest.load import (
    LoadedMAS,
    load_agent_for_bench,
    load_agent_runtime_entry,
    load_mas_config,
    load_overlay_as_spec,
)

__all__ = [
    "LoadedMAS",
    "load_mas_config",
    "load_agent_for_bench",
    "load_agent_runtime_entry",
    "load_overlay_as_spec",
]
