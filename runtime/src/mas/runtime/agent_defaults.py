#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Canonical agent defaults for lab/controller discovery and eval helpers.

Plugin slots (design pattern, context manager, assembler) live in
``defaults.yaml`` and can be overridden per-workspace via ``config.yaml``.
``models[].model: any`` is the compiled sentinel — ``defaults.model`` fills
it at engine time and is never written into the committed spec.
"""

from __future__ import annotations

from typing import Any


def default_pattern_plugin_id() -> str:
    """Registry id for ``spec.design_pattern`` when manifest omits type/ref."""
    from mas.runtime.registry import get_registry

    return get_registry().default_for("design_pattern")


def default_context_manager_id() -> str:
    """Registry id for ``spec.context_manager`` when manifest omits type/ref."""
    from mas.runtime.registry import get_registry

    return get_registry().default_for("context_manager")


def default_assembler_id() -> str:
    """Registry id for ``spec.assembler`` when manifest omits type/ref."""
    from mas.runtime.registry import get_registry

    return get_registry().default_for("assembler") or "assembler"


def default_model() -> str:
    """Package/workspace default LLM model id (``defaults.yaml`` + ``config.yaml``)."""
    from mas.runtime.registry.defaults import load_defaults

    return load_defaults().get("model", "gpt-4o-mini")


def resolve_default_model(workspace: Any = None) -> str:
    """Resolve default LLM model, preferring an explicit ``workspace`` object.

    Precedence: ``workspace.default_model`` (attribute or callable, if truthy)
    -> ``config.yaml``'s ``defaults.model`` -> the package default from
    ``defaults.yaml``.
    """
    if workspace is not None:
        dm = getattr(workspace, "default_model", None)
        if callable(dm):
            dm = dm()
        if dm:
            return str(dm)

    return default_model()


def agent_defaults(workspace: Any = None) -> dict[str, Any]:
    """Default agent spec fragment for UI/catalog (not a full manifest).

    ``models[].model: any`` is the compiled sentinel — local ``config.yaml``
    ``defaults.model`` fills it at engine time. Do not bake the workspace
    model into the spec (that would hide the pin from the committed YAML).
    """
    _ = workspace
    return {
        "design_pattern": {"type": default_pattern_plugin_id()},
        "models": [{"id": "main", "model": "any"}],
    }
