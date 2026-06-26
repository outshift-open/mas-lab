#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Library-scoped experiment definition CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from mas.lab.controller.models import SaveExperimentRequest
from mas.lab.controller.routes._api import deps, jobs, LIBRARIES_DIR, validate_pipeline_yaml

router = APIRouter()


@router.get("/api/libraries/{library_name}/experiments", tags=["Libraries"])
async def list_library_experiments(library_name: str):
    """List available experiment definitions with metadata."""
    experiments = deps.get_manifest_store().list_experiments(library_name)
    for exp in experiments:
        exp.setdefault("library", library_name)
    return {"experiments": experiments}


@router.post("/api/libraries/{library_name}/experiments", tags=["Libraries"], status_code=201)
async def create_experiment(library_name: str, req: SaveExperimentRequest):
    """Create a new experiment definition in the library's experiments/ directory."""
    lib_dir = deps.get_library_path(library_name)
    exp_dir = lib_dir / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{req.name}.yaml" if not req.name.endswith(".yaml") else req.name
    file_path = exp_dir / filename

    if file_path.exists():
        raise HTTPException(status_code=409, detail=f"Experiment '{req.name}' already exists")

    file_path.write_text(req.content, encoding="utf-8")
    return {"name": req.name, "filename": filename}


@router.get("/api/libraries/{library_name}/experiments/{experiment_name}", tags=["Libraries"])
async def get_library_experiment(library_name: str, experiment_name: str):
    """Return the content of a specific experiment definition."""
    store = deps.get_manifest_store()
    lib_dir = deps.get_library_path(library_name)
    filename = f"{experiment_name}.yaml" if not experiment_name.endswith(".yaml") else experiment_name
    candidates = [
        lib_dir / "experiments" / filename,
        lib_dir / filename,
    ]
    candidates.extend(
        p for p in store._registry._iter_experiment_files(lib_dir)
        if p.name == filename or p.stem == experiment_name
    )
    file_path = next((p for p in candidates if p.exists()), None)

    if file_path is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_name}' not found")

    return {
        "name": experiment_name,
        "filename": file_path.name,
        "content": file_path.read_text(encoding="utf-8"),
    }


@router.put("/api/libraries/{library_name}/experiments/{experiment_name}", tags=["Libraries"])
async def update_experiment(library_name: str, experiment_name: str, req: SaveExperimentRequest):
    """Update an existing experiment definition. Supports rename via req.name."""
    lib_dir = deps.get_library_path(library_name)
    exp_dir = lib_dir / "experiments"

    old_filename = f"{experiment_name}.yaml" if not experiment_name.endswith(".yaml") else experiment_name
    old_path = exp_dir / old_filename

    if not old_path.exists():
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_name}' not found")

    new_filename = f"{req.name}.yaml" if not req.name.endswith(".yaml") else req.name
    new_path = exp_dir / new_filename

    if req.name != experiment_name and new_path.exists():
        raise HTTPException(status_code=409, detail=f"Experiment '{req.name}' already exists")

    if old_path != new_path:
        old_path.unlink()
    new_path.write_text(req.content, encoding="utf-8")
    return {"name": req.name, "filename": new_filename}


@router.delete("/api/libraries/{library_name}/experiments/{experiment_name}", tags=["Libraries"])
async def delete_library_experiment(library_name: str, experiment_name: str):
    """Delete an experiment definition."""
    lib_dir = deps.get_library_path(library_name)
    filename = f"{experiment_name}.yaml" if not experiment_name.endswith(".yaml") else experiment_name
    file_path = lib_dir / "experiments" / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_name}' not found")

    file_path.unlink()
    return {"deleted": experiment_name}
