#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dataset CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from mas.lab.controller.deps import ensure_yaml_ext
from mas.lab.controller.models import SaveDatasetRequest
from mas.lab.controller.routes._api import deps, jobs, LIBRARIES_DIR, validate_pipeline_yaml

router = APIRouter()


@router.get("/api/libraries/{library_name}/datasets", tags=["Libraries"])
def list_datasets(library_name: str):
    """List available dataset YAML files under datasets/."""
    datasets = deps.get_manifest_store().list_datasets_meta(library_name)
    return {"datasets": datasets}


@router.post("/api/libraries/{library_name}/datasets", tags=["Libraries"], status_code=201)
def create_dataset(library_name: str, req: SaveDatasetRequest):
    """Create a new dataset file in the library's datasets/ directory."""
    lib_dir = deps.get_library_path(library_name)
    datasets_dir = lib_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    filename = ensure_yaml_ext(req.name)
    file_path = datasets_dir / filename

    if file_path.exists():
        raise HTTPException(status_code=409, detail=f"Dataset '{filename}' already exists")

    file_path.write_text(req.content, encoding="utf-8")
    return {"name": filename}


@router.get("/api/libraries/{library_name}/datasets/{dataset_name:path}", tags=["Libraries"])
def get_dataset(library_name: str, dataset_name: str):
    """Return the content of a specific dataset."""
    lib_dir = deps.get_library_path(library_name)
    file_path = lib_dir / "datasets" / dataset_name
    if not file_path.exists() and not dataset_name.lower().endswith((".yaml", ".yml")):
        file_path = lib_dir / "datasets" / f"{dataset_name}.yaml"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' not found")

    return {"name": file_path.name, "content": file_path.read_text(encoding="utf-8")}


@router.put("/api/libraries/{library_name}/datasets/{dataset_name:path}", tags=["Libraries"])
def update_dataset(library_name: str, dataset_name: str, req: SaveDatasetRequest):
    """Update an existing dataset. Supports rename via req.name."""
    lib_dir = deps.get_library_path(library_name)
    datasets_dir = lib_dir / "datasets"

    dataset_name = ensure_yaml_ext(dataset_name)
    new_name = ensure_yaml_ext(req.name)

    old_path = datasets_dir / dataset_name
    if not old_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' not found")

    new_path = datasets_dir / new_name
    if new_name != dataset_name and new_path.exists():
        raise HTTPException(status_code=409, detail=f"Dataset '{new_name}' already exists")

    if old_path != new_path:
        old_path.unlink()
    new_path.write_text(req.content, encoding="utf-8")
    return {"name": new_name}


@router.delete("/api/libraries/{library_name}/datasets/{dataset_name:path}", tags=["Libraries"])
def delete_dataset(library_name: str, dataset_name: str):
    """Delete a dataset file."""
    lib_dir = deps.get_library_path(library_name)
    dataset_name = ensure_yaml_ext(dataset_name)
    file_path = lib_dir / "datasets" / dataset_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' not found")

    file_path.unlink()
    return {"deleted": dataset_name}
