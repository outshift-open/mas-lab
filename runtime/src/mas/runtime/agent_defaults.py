#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Canonical agent defaults for lab/controller discovery and eval helpers.

The actual default values (model, design pattern, context manager) are no
longer hardcoded constants here -- they live in ``defaults.yaml`` (see
``mas.runtime.registry.defaults``) and can be overridden per-workspace via
the ``defaults:`` block in ``config.yaml``, exactly like ``aliases:``. This
module is just the stable, workspace-aware accessor surface used by the
rest of the codebase.
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
    """Default agent spec fragment for UI/catalog (not a full manifest)."""
    model = resolve_default_model(workspace)
    return {
        "design_pattern": {"type": default_pattern_plugin_id()},
        "models": [{"id": "main", "model": model}],
    }
