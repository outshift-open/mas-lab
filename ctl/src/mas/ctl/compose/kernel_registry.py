#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kernel runtime registry — IDs from component-registry.yaml."""

from __future__ import annotations

from typing import Protocol

from mas.ctl.compose.models import EffectiveBindManifest, RuntimeId
from mas.ctl.registry.catalog import UnknownComponentError, get_runtime, import_class, list_runtime_ids


class KernelBackend(Protocol):
    """Materialized kernel for one agent from EffectiveBindManifest slice."""

    backend_id: RuntimeId

    def create_agent_runtime(self, bind: EffectiveBindManifest, agent_id: str) -> object:
        """Return RuntimeInstance from EffectiveBindManifest slice."""


_BACKENDS: dict[str, type] = {}


def register_runtime(runtime_id: str, cls: type) -> None:
    validate_runtime_id(runtime_id)
    _BACKENDS[runtime_id] = cls


def list_registered_runtimes() -> list[str]:
    _ensure_registered()
    return sorted(_BACKENDS.keys())


# Back-compat aliases for introspection / older imports
list_registered_backends = list_registered_runtimes
register_kernel_backend = register_runtime


def get_runtime_backend(
    runtime_id: RuntimeId,
    *,
    resolved_infra=None,
) -> KernelBackend:
    _ensure_registered()
    if runtime_id not in _BACKENDS:
        raise KeyError(f"runtime {runtime_id!r} not registered (see component-registry.yaml)")
    cls = _BACKENDS[runtime_id]
    if runtime_id == "python-v2":
        return cls(resolved_infra=resolved_infra)  # type: ignore[call-arg]
    return cls()  # type: ignore[call-arg]


get_kernel_backend = get_runtime_backend


def validate_runtime_id(runtime_id: str) -> str:
    from mas.ctl.registry.catalog import validate_runtime_id as _validate

    return _validate(runtime_id)


_CATALOG_REGISTERED = False


def _register_from_catalog() -> None:
    global _CATALOG_REGISTERED
    if _CATALOG_REGISTERED:
        return
    for entry in list_runtime_ids(include_planned=False):
        if entry in _BACKENDS:
            continue
        spec = get_runtime(entry)
        if not spec.module:
            continue
        cls = import_class(spec.module)
        register_runtime(entry, cls)
    _CATALOG_REGISTERED = True


def _ensure_registered() -> None:
    _register_from_catalog()
