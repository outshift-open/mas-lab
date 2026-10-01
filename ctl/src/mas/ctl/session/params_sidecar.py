#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Hand manifest ``spec.params`` to tools through the agent context."""

from __future__ import annotations

from typing import Any


def apply_runtime_params_to_instance(params: dict[str, Any], instance: Any) -> None:
    """Expose params to in-process tools as ``ctx.runtime_params``."""
    if not params:
        return
    ctx = getattr(getattr(instance, "driver", None), "ctx", None)
    if ctx is None:
        return
    ctx.runtime_params = dict(params)


def params_from_mas_config(mas_config: dict[str, Any]) -> dict[str, Any]:
    spec = mas_config.get("spec", mas_config) if isinstance(mas_config, dict) else {}
    raw = spec.get("params") or {}
    return dict(raw) if isinstance(raw, dict) else {}
