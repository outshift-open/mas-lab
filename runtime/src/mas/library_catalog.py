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
        # A genuinely absent library.yaml is a valid, optional case.
        return {}
    # A present-but-malformed library.yaml is a real configuration error, not
    # an optional-missing file: fail loud so a half-saved / broken manifest
    # surfaces immediately at discovery time. Swallowing it here silently
    # registers *zero* plugins for the library, which only shows up far
    # downstream as a confusing "no plugin registered for ..." error (this is
    # exactly how a corrupt library.yaml stayed hidden through a whole commit).
    try:
        data = load_yaml_file(manifest_path)
    except Exception as exc:
        raise ValueError(f"Failed to parse library manifest {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"Library manifest {manifest_path} must be a mapping, got {type(data).__name__}."
        )
    return data


def _resolve_manifest_entry(root: Path, rel: str) -> Path | None:
    if not isinstance(rel, str) or not rel.strip():
        return None
    candidate = (root / rel.strip()).resolve()
    return candidate if candidate.exists() else None


def _is_app_directory(path: Path) -> bool:
    """True when *path* is a MAS app root (``mas.yaml`` or standalone agent layout)."""
    if (path / "mas.yaml").is_file() or (path / "mas-bench.yaml").is_file():
        return True
    if (path / "agent.yaml").is_file():
        return True
    agents_dir = path / "agents"
    return agents_dir.is_dir() and any(agents_dir.glob("*.yaml"))


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
        if path is not None and path.is_dir() and _is_app_directory(path):
            found[name] = path
    return found


def _discover_apps_from_scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return found
    for app_dir in sorted(apps_dir.iterdir()):
        if app_dir.is_dir() and _is_app_directory(app_dir):
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


def _tool_manifest_in_dir(path: Path) -> Path | None:
    """Return a ``*.tool.yaml`` file for *path* (the file itself, or one inside a dir)."""
    if path.is_file() and path.name.endswith(".tool.yaml"):
        return path.resolve()
    if path.is_dir():
        matches = sorted(path.glob("*.tool.yaml"))
        if matches:
            return matches[0].resolve()
    return None


def find_tool_manifest(name: str) -> Path | None:
    """Resolve a bare tool *name* to its ``*.tool.yaml`` file across library roots.

    This is the tool-name → implementation catalog: a name written in
    ``spec.tools`` (from YAML or a ``--tool`` CLI flag) is mapped to the tool
    manifest that declares its implementation. Resolution order per library
    root: the ``library.yaml`` ``tools:`` map, then a flat
    ``tools/<name>.tool.yaml``, then ``tools/<name>/*.tool.yaml``. Returns
    ``None`` when no library declares the name.
    """
    if not name or not isinstance(name, str):
        return None
    for root in discover_library_roots():
        manifest = _load_library_manifest(root)
        tools = manifest.get("tools")
        if isinstance(tools, dict):
            rel = tools.get(name)
            if isinstance(rel, str) and rel.strip():
                entry = _resolve_manifest_entry(root, rel)
                if entry is not None and (found := _tool_manifest_in_dir(entry)) is not None:
                    return found
        for candidate in (root / "tools" / f"{name}.tool.yaml", root / "tools" / name):
            if candidate.exists() and (found := _tool_manifest_in_dir(candidate)) is not None:
                return found
    return None


def _declares_plugins(manifest: dict[str, Any]) -> bool:
    """True when ``library.yaml`` declares plugin-manifest content directly.

    Signalled by the presence of the ``types:`` and/or ``plugins:`` keys
    (``plugins:`` here is always a *list* of plugin declarations, see
    :mod:`mas.runtime.registry.bootstrap`). This check is a key-presence
    test, not a shape guess: the name->path split-file catalog below uses
    a differently-named key (``plugin_manifests:``) precisely so the two
    conventions never need to be disambiguated by inspecting value types.
    """
    return bool(manifest.get("types")) or bool(manifest.get("plugins"))


def _discover_plugin_manifests_from_catalog(root: Path, manifest: dict[str, Any]) -> list[Path]:
    """Explicit ``plugin_manifests:`` catalog in ``library.yaml`` (name -> relative path).

    Only used when a library wants to split its plugin declarations across
    multiple files; most libraries should just declare ``types:``/``plugins:``
    directly in ``library.yaml`` (see :func:`_declares_plugins`).
    """
    found: list[Path] = []
    catalog = manifest.get("plugin_manifests")
    if not isinstance(catalog, dict):
        return found
    for name, rel in catalog.items():
        if not isinstance(name, str):
            continue
        path = _resolve_manifest_entry(root, rel)
        if path is not None and path.is_file():
            found.append(path)
    return found


def _discover_plugin_manifests_from_scan(root: Path) -> list[Path]:
    """Convention fallback: any ``*.plugins.yaml`` under ``<root>/plugins/``.

    Same rationale as :func:`_discover_plugin_manifests_from_catalog` — an
    escape hatch for libraries that split plugin declarations across
    multiple files, not the primary mechanism.
    """
    found: list[Path] = []
    plugins_dir = root / "plugins"
    if not plugins_dir.is_dir():
        return found
    for path in sorted(plugins_dir.rglob("*.plugins.yaml")):
        found.append(path.resolve())
    return found


def discover_plugin_manifests() -> list[Path]:
    """Resolve plugin manifests (generic ``types:``/``plugins:`` YAML, see
    :mod:`mas.runtime.registry.bootstrap`) from every known library root.

    ``library.yaml`` *is* the plugin manifest: it doubles as library
    metadata (``kind: Library`` — name/description/version/module_base,
    consumed by :func:`discover_apps`/:func:`discover_datasets`/
    :func:`discover_tools`) and, when it declares ``types:``/``plugins:``
    directly, as the manifest fed straight into ``register_manifest_data``.
    A library only needs a separate ``*.plugins.yaml`` file if it genuinely
    wants to split its plugin declarations across multiple files, via
    either:

    1. An explicit ``plugin_manifests:`` catalog in ``library.yaml`` (name -> relative path).
    2. A scan fallback: any ``<root>/plugins/*.plugins.yaml``.

    All three are additive per root; duplicates across roots are not
    deduplicated here — :func:`~mas.runtime.registry.bootstrap.load_registry`
    registers each file exactly once per process since it iterates this list
    directly.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for root in discover_library_roots():
        manifest = _load_library_manifest(root)
        candidates: list[Path] = []
        if _declares_plugins(manifest):
            candidates.append((root / "library.yaml").resolve())
        candidates.extend(_discover_plugin_manifests_from_catalog(root, manifest))
        candidates.extend(_discover_plugin_manifests_from_scan(root))
        for path in candidates:
            if path not in seen:
                seen.add(path)
                found.append(path)
    return found
