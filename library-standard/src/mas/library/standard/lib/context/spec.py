#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Read ``spec.context_manager`` for plugins (lenient: malformed → empty binding)."""

from __future__ import annotations

from typing import Any

from mas.runtime.spec.plugin_binding import normalize_plugin_binding_lenient

_SUMMARISING_TYPES = frozenset({"summarising", "summarizing"})


def is_summarising_context_manager(cm: dict[str, Any] | str | None) -> bool:
    binding = normalize_plugin_binding_lenient(cm, field="spec.context_manager")
    type_name = str(binding.get("type") or "").strip().lower().replace("_", "-")
    return type_name in _SUMMARISING_TYPES


def context_manager_spec(manifest: dict | None) -> dict[str, Any]:
    spec = (manifest or {}).get("spec") or {}
    return normalize_plugin_binding_lenient(spec.get("context_manager"), field="spec.context_manager")
