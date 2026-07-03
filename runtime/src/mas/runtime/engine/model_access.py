#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load infra-declared model access plugins (e.g. MockModelAccess)."""

from __future__ import annotations

import importlib
from typing import Any


class ModelAccessLoadError(RuntimeError):
    """``llm_proxy['model_access']`` was configured but could not be instantiated."""


def load_model_access(cfg: dict[str, Any] | None) -> Any | None:
    """Instantiate model access from ``llm_proxy['model_access']`` infra config."""
    if not isinstance(cfg, dict) or not cfg:
        return None
    module_path = cfg.get("module_path")
    class_name = cfg.get("class_name")
    if not module_path or not class_name:
        return None
    try:
        mod = importlib.import_module(str(module_path))
        cls = getattr(mod, str(class_name))
        params = dict(cfg.get("params") or {})
        return cls(**params)
    except Exception as exc:
        raise ModelAccessLoadError(
            f"Failed to load model access {module_path}.{class_name}: {exc}"
        ) from exc
