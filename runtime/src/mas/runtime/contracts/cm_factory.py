#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""CMFactory — thin facade over :func:`mas.runtime.registry.get_registry`."""

from __future__ import annotations

from typing import Any

from mas.runtime.contracts.context_manager_contract import ContextManagerContract
from mas.runtime.registry import get_registry


class CMFactory:
    """Instantiate ``spec.context_manager`` via the runtime registry."""

    @classmethod
    def create(
        cls,
        spec: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        params: dict[str, Any] | None = None,
        manifest: dict | None = None,
    ) -> ContextManagerContract:
        binding: dict[str, Any] = dict(spec or {})
        if manifest is not None and not binding:
            raw = (manifest.get("spec") or {}).get("context_manager") or {}
            binding = raw if isinstance(raw, dict) else {}
        if name:
            binding = {**binding, "type": name}
        if params:
            binding = {**binding, "params": {**(binding.get("params") or {}), **params}}
        instance = get_registry().create("context_manager", binding, manifest=manifest)
        if not isinstance(instance, ContextManagerContract):
            raise TypeError(f"{type(instance).__name__} is not a ContextManagerContract")
        return instance

    @classmethod
    def create_from_manifest(cls, manifest: dict | None) -> ContextManagerContract:
        return cls.create(manifest=manifest)
