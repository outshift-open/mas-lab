#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Reuse registry plugin instances across turns on the same ctx + manifest."""

from __future__ import annotations

from typing import Any

from mas.runtime.contracts.context_manager_contract import ContextManagerContract
from mas.runtime.contracts.cm_factory import CMFactory
from mas.runtime.registry import get_registry


def cached_context_manager(ctx: Any, manifest: dict | None) -> ContextManagerContract:
    if manifest is getattr(ctx, "_assembly_cm_manifest", None):
        cached = getattr(ctx, "_assembly_cm", None)
        if cached is not None:
            return cached
    cm = CMFactory.create(manifest=manifest, engine=getattr(ctx, "engine", None))
    ctx._assembly_cm = cm
    ctx._assembly_cm_manifest = manifest
    return cm


def cached_assembler(ctx: Any, manifest: dict | None) -> Any:
    """Registry ``assembler`` (default ``assembler``), cached per ctx."""
    if manifest is getattr(ctx, "_assembly_assembler_manifest", None):
        cached = getattr(ctx, "_assembly_assembler", None)
        if cached is not None:
            return cached
    plugin = get_registry().create("assembler", manifest=manifest)
    ctx._assembly_assembler = plugin
    ctx._assembly_assembler_manifest = manifest
    return plugin
