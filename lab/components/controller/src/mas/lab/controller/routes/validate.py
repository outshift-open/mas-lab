#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest validation endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from mas.lab.controller.manifest_validation import validate_manifest_yaml_content
from mas.lab.controller.models import ValidateRequest
from mas.lab.controller.routes._api import deps

router = APIRouter()


@router.post("/api/libraries/{library_name}/validate", tags=["Libraries"])
async def validate_manifest(library_name: str, req: ValidateRequest):
    """Validate an agent or MAS manifest in-process. Resolves refs relative to the library dir."""
    lib_dir = deps.get_library_path(library_name)
    return validate_manifest_yaml_content(req.manifest_yaml, base_dir=lib_dir, resolve_refs=True)
