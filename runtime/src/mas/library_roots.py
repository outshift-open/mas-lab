#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover manifest library roots from installed packages and workspace paths."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
import json
from pathlib import Path

_MODULE_DIST: dict[str, str] = {
    "mas.library.samples": "mas-library-samples",
    "mas.library.standard": "mas-library-standard",
}


def _find_library_root(start: Path) -> Path | None:
    """Walk upward from *start* to find a directory with ``library.yaml``."""
    here = start if start.is_dir() else start.parent
    for parent in [here, *here.parents]:
        if (parent / "library.yaml").is_file():
            return parent.resolve()
    return None


def _root_from_editable_distribution(module: str) -> Path | None:
    dist_name = _MODULE_DIST.get(module)
    if not dist_name:
        return None
    try:
        dist = importlib.metadata.distribution(dist_name)
        data = json.loads(dist.read_text("direct_url.json"))
        url = data.get("url", "")
        if url.startswith("file://"):
            return _find_library_root(Path(url[7:]))
    except Exception:
        return None
    return None


def resolve_manifest_library_package(module: str) -> Path | None:
    """Resolve the on-disk root for a ``mas.runtime.manifest_libraries`` package."""
    try:
        mod = importlib.import_module(module)
        root_fn = getattr(mod, "package_root", None)
        if callable(root_fn):
            return Path(root_fn()).resolve()
        mod_file = getattr(mod, "__file__", None)
        if mod_file:
            found = _find_library_root(Path(mod_file).resolve())
            if found is not None:
                return found
    except Exception:
        pass

    fallback = _root_from_editable_distribution(module)
    if fallback is not None:
        return fallback

    try:
        return Path(importlib.resources.files(module)).resolve()
    except Exception:
        return None


def _installed_library_roots() -> list[Path]:
    """Return roots for packages registered via ``mas.runtime.manifest_libraries``."""
    roots: list[Path] = []
    try:
        eps = importlib.metadata.entry_points(group="mas.runtime.manifest_libraries")
    except Exception:
        return roots

    for ep in eps:
        root = resolve_manifest_library_package(ep.value)
        if root is not None:
            roots.append(root)
    return roots


def discover_library_roots() -> list[Path]:
    """Return library roots from installed packages and optional workspace paths."""
    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        resolved = path.resolve()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)

    for path in _installed_library_roots():
        _add(path)

    from mas.runtime.workspace_config import RuntimeWorkspaceConfig

    ws = RuntimeWorkspaceConfig.load()
    if ws.found and ws.root is not None:
        for rel in ws.manifest_libraries.values():
            if isinstance(rel, str) and rel.strip():
                _add(ws.root / rel)

    return roots
