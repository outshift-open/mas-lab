#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Registry and discovery endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from mas.lab.controller.routes._api import deps, jobs, LIBRARIES_DIR, validate_pipeline_yaml

router = APIRouter()


@router.get("/api/registry", tags=["Registry"])
async def list_registry():
    """Unified lab + runtime registry catalog."""
    from mas.lab.controller.lab_registry import get_lab_registry

    ws = getattr(deps.get_manifest_store(), "_workspace", None)
    return {"registry": get_lab_registry(ws).catalog()}


@router.get("/api/defaults", tags=["Registry"])
async def get_defaults():
    """Agent and infra defaults (design pattern, model) for UI and playground."""
    from mas.lab.controller.lab_registry import get_lab_registry

    ws = getattr(deps.get_manifest_store(), "_workspace", None)
    reg = get_lab_registry(ws)
    return {
        "agent": reg.agent_defaults(),
        "default_model": reg.default_model(),
    }


@router.get("/api/discovery", tags=["Registry"])
async def get_discovery_report():
    """Paths scanned, libraries resolved, and runtime entry points (debug)."""
    store = deps.get_manifest_store()
    return store._registry.discovery_report()
