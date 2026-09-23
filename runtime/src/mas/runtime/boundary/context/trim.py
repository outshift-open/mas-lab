#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Context manager manifest helpers."""

from __future__ import annotations

from typing import Any

CONTEXT_MANAGER_TYPE_SUMMARISING = "summarising"
_SUMMARISING_TYPES = frozenset({"summarising", "summarizing"})


def is_summarising_context_manager(cm: dict[str, Any] | None) -> bool:
    if not isinstance(cm, dict):
        return False
    type_name = str(cm.get("type") or "").strip().lower().replace("_", "-")
    return type_name in _SUMMARISING_TYPES


def context_manager_spec(manifest: dict | None) -> dict[str, Any]:
    spec = (manifest or {}).get("spec") or {}
    cm = spec.get("context_manager") or {}
    return cm if isinstance(cm, dict) else {}
