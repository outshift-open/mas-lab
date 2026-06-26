#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Filesystem discovery for apps, datasets, and tools inside manifest libraries."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mas.library_roots import discover_library_roots
from mas.runtime.spec.source import load_yaml_file

logger = logging.getLogger(__name__)


def _load_library_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "library.yaml"
    if not manifest_path.is_file():
        return {}
    try:
        data = load_yaml_file(manifest_path)
    except Exception:
        logger.warning("Failed to parse library manifest %s; ignoring.", manifest_path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_manifest_entry(root: Path, rel: str) -> Path | None:
    if not isinstance(rel, str) or not rel.strip():
        return None
    candidate = (root / rel.strip()).resolve()
    return candidate if candidate.exists() else None


def _dataset_keys(path: Path, datasets_dir: Path) -> list[str]:
    keys: list[str] = []
    try:
        data = load_yaml_file(path)
    except Exception:
        logger.warning("Failed to parse dataset manifest %s; ignoring.", path, exc_info=True)
        data = {}

    meta_name = (data.get("metadata") or {}).get("name") or data.get("name")
    if isinstance(meta_name, str) and meta_name.strip():
        keys.append(meta_name.strip())

    rel = path.relative_to(datasets_dir)
    if rel.parent != Path("."):
        keys.append(f"{rel.parent.name}-{path.stem}")
    keys.append(path.stem)
    return keys


def _discover_apps_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    apps = manifest.get("apps")
    if not isinstance(apps, dict):
        return found

    for name, rel in apps.items():
        if not isinstance(name, str):
            continue
        path = _resolve_manifest_entry(root, rel)
        if path is not None and path.is_dir() and (path / "mas.yaml").is_file():
            found[name] = path
    return found


def _discover_apps_from_scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return found
    for app_dir in sorted(apps_dir.iterdir()):
        if app_dir.is_dir() and (app_dir / "mas.yaml").is_file():
            found[app_dir.name] = app_dir.resolve()
    return found


def discover_apps() -> dict[str, Path]:
    """Resolve apps from ``library.yaml`` first, then ``apps/<name>/mas.yaml`` scan."""
    found: dict[str, Path] = {}
    for root in discover_library_roots():
        manifest = _load_library_manifest(root)
        for name, path in _discover_apps_from_manifest(root, manifest).items():
            found[name] = path
        for name, path in _discover_apps_from_scan(root).items():
            found.setdefault(name, path)
    return found


def _discover_datasets_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict):
        return found

    for name, rel in datasets.items():
        if not isinstance(name, str):
            continue
        path = _resolve_manifest_entry(root, rel)
        if path is not None and path.is_file():
            found[name] = path
    return found


def _discover_datasets_from_scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    datasets_dir = root / "datasets"
    if not datasets_dir.is_dir():
        return found
    for path in sorted(datasets_dir.rglob("*.yaml")):
        resolved = path.resolve()
        for key in _dataset_keys(path, datasets_dir):
            found.setdefault(key, resolved)
    return found


def discover_datasets() -> dict[str, Path]:
    """Resolve datasets from ``library.yaml`` first, then ``datasets/**/*.yaml`` scan."""
    found: dict[str, Path] = {}
    for root in discover_library_roots():
        manifest = _load_library_manifest(root)
        for name, path in _discover_datasets_from_manifest(root, manifest).items():
            found[name] = path
        for name, path in _discover_datasets_from_scan(root).items():
            found.setdefault(name, path)
    return found


def _discover_tools_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    tools = manifest.get("tools")
    if not isinstance(tools, dict):
        return found

    for name, rel in tools.items():
        if not isinstance(name, str):
            continue
        path = _resolve_manifest_entry(root, rel)
        if path is not None and path.is_dir() and any(path.glob("*.tool.yaml")):
            found[name] = path
    return found


def _discover_tools_from_scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    tools_dir = root / "tools"
    if not tools_dir.is_dir():
        return found
    for tool_dir in sorted(tools_dir.iterdir()):
        if tool_dir.is_dir() and any(tool_dir.glob("*.tool.yaml")):
            found[tool_dir.name] = tool_dir.resolve()
    return found


def discover_tools() -> dict[str, Path]:
    """Resolve tools from ``library.yaml`` first, then ``tools/<name>/*.tool.yaml`` scan."""
    found: dict[str, Path] = {}
    for root in discover_library_roots():
        manifest = _load_library_manifest(root)
        for name, path in _discover_tools_from_manifest(root, manifest).items():
            found[name] = path
        for name, path in _discover_tools_from_scan(root).items():
            found.setdefault(name, path)
    return found
