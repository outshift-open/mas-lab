#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Canonical agent defaults for lab/controller discovery and eval helpers."""

from __future__ import annotations

from typing import Any

CANONICAL_DEFAULT_MODEL = "gpt-4o-mini"
CANONICAL_DEFAULT_DP = "react"


def default_pattern_plugin_id() -> str:
    """Registry id for ``spec.design_pattern`` when manifest omits type/ref."""
    from mas.runtime.registry import SPEC_DEFAULTS

    return SPEC_DEFAULTS["design_pattern"]


def default_context_manager_id() -> str:
    from mas.runtime.registry import SPEC_DEFAULTS

    return SPEC_DEFAULTS["context_manager"]


def resolve_default_model(workspace: Any = None) -> str:
    """Resolve workspace default LLM model with canonical fallback."""
    if workspace is not None:
        dm = getattr(workspace, "default_model", None)
        if callable(dm):
            dm = dm()
        if dm:
            return str(dm)

    from mas.runtime.workspace_config import RuntimeWorkspaceConfig

    ws = RuntimeWorkspaceConfig.load()
    if ws.found and ws.default_model:
        return str(ws.default_model)

    return CANONICAL_DEFAULT_MODEL


def agent_defaults(workspace: Any = None) -> dict[str, Any]:
    """Default agent spec fragment for UI/catalog (not a full manifest)."""
    model = resolve_default_model(workspace)
    return {
        "design_pattern": {"type": CANONICAL_DEFAULT_DP},
        "models": [{"id": "main", "model": model}],
    }
