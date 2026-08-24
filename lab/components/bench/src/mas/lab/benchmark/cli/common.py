#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""Shared benchmark CLI helpers."""

from pathlib import Path
from typing import Optional

from mas.lab.benchmark.cache import get_trace_cache_dir as _get_trace_cache_dir
from mas.library_roots import find_ancestor_with_file
from mas.runtime.constants import LAB_CONFIG_FILENAME

def _resolve_run_manager_dir(explicit: Optional[Path]) -> Path:
    """Return the primary benchmark output root from CLI or active config."""
    if explicit is not None:
        return explicit.resolve()
    _lab_dir = find_ancestor_with_file(
        Path.cwd().resolve(), LAB_CONFIG_FILENAME, stop_at_suffix=".lab"
    )
    if _lab_dir is not None:
        try:
            from mas.runtime.spec.source import load_yaml_file

            _raw = load_yaml_file(_lab_dir / LAB_CONFIG_FILENAME)
            _out = _raw.get("lab", {}).get("output_dir", "output")
            return (_lab_dir / _out).resolve()
        except Exception:
            logger.debug('suppressed', exc_info=True)
    from mas.lab import paths as _paths

    return _paths.labs_root()

