#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime identity — validated against component-registry.yaml."""

from __future__ import annotations

from typing import Any

from mas.ctl.registry.catalog import validate_runtime_id as _validate_catalog

from mas.runtime.constants import DEFAULT_RUNTIME_ID

__all__ = [
    "DEFAULT_RUNTIME_ID",
    "is_default_runtime",
    "normalize_runtime_id",
    "runtime_id_from_deployment",
]


def normalize_runtime_id(value: str | None) -> str:
    if not value:
        return DEFAULT_RUNTIME_ID
    return _validate_catalog(str(value).strip())


def runtime_id_from_deployment(deployment: dict[str, Any]) -> str | None:
    """Read ``spec.runtime_id`` — sole deployment field for kernel selection."""
    spec = deployment.get("spec") or deployment
    runtime_id = spec.get("runtime_id")
    if isinstance(runtime_id, str) and runtime_id.strip():
        return normalize_runtime_id(runtime_id)
    return None


def is_default_runtime(runtime_id: str) -> bool:
    return normalize_runtime_id(runtime_id) == DEFAULT_RUNTIME_ID
