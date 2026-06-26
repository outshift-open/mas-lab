#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Context manager manifest helpers."""

from __future__ import annotations

from typing import Any


def context_manager_spec(manifest: dict | None) -> dict[str, Any]:
    spec = (manifest or {}).get("spec") or {}
    cm = spec.get("context_manager") or {}
    return cm if isinstance(cm, dict) else {}
