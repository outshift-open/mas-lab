#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Content-addressed trace cache helpers."""
from mas.lab.benchmark.cache.trace_store import (
    compute_run_hash,
    resolve_run_events_path,
    trace_cache_roots,
    extract_flavour_info,
    get_trace_cache_dir,
    link_trace_to_cache_entry,
    materialize_config,
    write_cache_inputs,
    write_run_info,
    write_run_result,
)

__all__ = [
    "compute_run_hash",
    "extract_flavour_info",
    "get_trace_cache_dir",
    "link_trace_to_cache_entry",
    "materialize_config",
    "resolve_run_events_path",
    "trace_cache_roots",
    "write_cache_inputs",
    "write_run_info",
    "write_run_result",
]
