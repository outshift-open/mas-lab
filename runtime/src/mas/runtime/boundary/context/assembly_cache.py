#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Reuse registry plugin instances across turns on the same ctx + manifest."""

from __future__ import annotations

from typing import Any

from mas.runtime.contracts.context_manager_contract import ContextManagerContract
from mas.runtime.contracts.cm_factory import CMFactory


def cached_context_manager(ctx: Any, manifest: dict | None) -> ContextManagerContract:
    if manifest is getattr(ctx, "_assembly_cm_manifest", None):
        cached = getattr(ctx, "_assembly_cm", None)
        if cached is not None:
            return cached
    cm = CMFactory.create(manifest=manifest)
    ctx._assembly_cm = cm
    ctx._assembly_cm_manifest = manifest
    return cm
