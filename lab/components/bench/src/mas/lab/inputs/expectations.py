#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``expectations``: generic ground truth plus a free-form ``details`` section.

``ground_truth`` and ``metrics`` are read by mas-lab's generic metrics. Anything
specific to an app or its evaluators lives under ``details`` and is opaque here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mas.lab.inputs.refs import resolve_text_slot

EXPECTATION_KEYS = frozenset({"ground_truth", "metrics", "details"})


def resolve_expectations(value: Any, base_path: Optional[Path], *, where: str) -> Dict[str, Any]:
    resolved = resolve_text_slot(value, base_path)
    if resolved is None:
        return {}
    if not isinstance(resolved, dict):
        raise TypeError(f"{where}: expectations must resolve to a mapping")
    unknown = sorted(set(resolved) - EXPECTATION_KEYS)
    if unknown:
        from mas.lab.deprecations import warn_deprecated

        warn_deprecated("dataset.legacy_expectations", where=where)
        details = dict(resolved.get("details") or {})
        clash = [key for key in unknown if key in details]
        if clash:
            raise ValueError(
                f"{where}: expectations keys {clash} already exist in details"
            )
        for key in unknown:
            details[key] = resolved[key]
        resolved = {
            key: value for key, value in resolved.items() if key in EXPECTATION_KEYS
        }
        resolved["details"] = details
    details = resolved.get("details")
    if details is not None and not isinstance(details, dict):
        raise TypeError(f"{where}: expectations.details must be a mapping")
    return dict(resolved)
