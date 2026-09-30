#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Filesystem discovery for apps, datasets, and tools inside manifest libraries."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from mas.library_roots import discover_library_roots
from mas.runtime.constants import LIBRARY_MANIFEST_FILENAME
from mas.runtime.spec.source import load_yaml_file
from mas.version_spec import (
    app_satisfies,
    parse_app_dependency,
    split_library_prefix,
    split_name_version,
    version_sort_key,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _load_library_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / LIBRARY_MANIFEST_FILENAME
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
    if not agents_dir.is_dir():
        return False
    if any(agents_dir.glob("*.yaml")):
        return True
    return any(agents_dir.glob("*/AGENT.md"))


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


def parse_library_ref(ref: str) -> tuple[str, str] | None:
    """Split ``library:object`` when *ref* is that form (not a filesystem path)."""
    scheme, object_id = split_library_prefix(ref)
    if scheme is None:
        return None
    return scheme, object_id


def parse_versioned_id(object_id: str) -> tuple[str, str | None]:
    """Split ``name@version``. Bare ``name`` means latest (``version is None``).

    Same separator as plugin ids (``react@v1``). Folder ``v2`` maps to ``@v2``.
    """
    return split_name_version(object_id)


def versioned_id(name: str, version: str | None) -> str:
    """Format ``name`` or ``name@version``."""
    if not version:
        return name
    ver = version if str(version).startswith("v") else f"v{version}"
    return f"{name}@{ver}"


class UnpinnedCatalogIdError(ValueError):
    """A spec used a versioned catalog id without ``@version``."""


def catalog_object_id(ref: str) -> str:
    """Strip an optional ``LIBRARY:`` prefix; leave filesystem paths unchanged."""
    parsed = parse_library_ref(str(ref or "").strip())
    return parsed[1] if parsed else str(ref or "").strip()


def require_pinned_catalog_id(
    ref: str,
    *,
    kind: str = "app",
    where: str = "spec",
) -> None:
    """Optional checker: reject a versioned catalog id that omits ``@version``.

    Loaders do **not** call this. Unpinned ``sre-triage`` is ``@latest``
    (highest ``v*`` folder), same as ``get_app`` / ``mas-ctl check``.
    """
    text = str(ref or "").strip()
    object_id = catalog_object_id(text)
    if not object_id or "/" in object_id:
        return
    name, ver = parse_versioned_id(object_id)
    if not name or ver:
        return
    catalog = discover_apps() if kind == "app" else discover_datasets()
    has_versions = any(
        parse_versioned_id(key)[0] == name and parse_versioned_id(key)[1]
        for key in catalog
    )
    if has_versions:
        raise UnpinnedCatalogIdError(
            f"{where}: {text!r} is a versioned {kind}; pin an explicit version "
            f"(e.g. {name}@v1). Specs must not depend on @latest."
        )


def _version_named_dirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return [
        child
        for child in sorted(path.iterdir())
        if child.is_dir() and child.name.startswith("v")
    ]


def _version_dirs(path: Path) -> list[Path]:
    return [child for child in _version_named_dirs(path) if _is_app_directory(child)]


def _register_catalog_entry(
    found: dict[str, Path], name: str, path: Path, version: str | None
) -> None:
    resolved = path.resolve()
    if version:
        found[versioned_id(name, version)] = resolved
    else:
        found.setdefault(name, resolved)


def _add_latest_aliases(found: dict[str, Path]) -> dict[str, Path]:
    """Bare ``name`` resolves to the highest ``name@version`` when versions exist."""
    by_name: dict[str, dict[str, Path]] = {}
    for key, path in found.items():
        name, ver = parse_versioned_id(key)
        if name and ver:
            by_name.setdefault(name, {})[ver] = path
    aliased = dict(found)
    for name, versions in by_name.items():
        latest = max(versions, key=version_sort_key)
        aliased.setdefault(name, versions[latest])
    return aliased


def _lookup_versioned(index: dict[str, Path], object_id: str) -> Path | None:
    if object_id in index:
        return index[object_id]
    name, ver = parse_versioned_id(object_id)
    if not name:
        return None
    if ver:
        return index.get(versioned_id(name, ver))
    return index.get(name)


def _discover_apps_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    """Index ``library.yaml`` ``apps:`` entries.

    A catalog key may be a family (``sre-triage: apps/sre-triage``) whose
    children are ``v*`` version folders, or an explicit version
    (``sre-triage@v2: apps/sre-triage/v2``).
    """
    found: dict[str, Path] = {}
    apps = manifest.get("apps")
    if not isinstance(apps, dict):
        return found

    for name, rel in apps.items():
        if not isinstance(name, str):
            continue
        path = _resolve_manifest_entry(root, rel)
        if path is None or not path.is_dir():
            continue
        key_name, key_ver = parse_versioned_id(name)
        versions = _version_dirs(path)
        if versions and not _is_app_directory(path):
            family = key_name or path.name
            for ver_dir in versions:
                _register_catalog_entry(found, family, ver_dir, ver_dir.name)
            continue
        if _is_app_directory(path):
            family = key_name or path.name
            version = key_ver
            if version is None and path.name.startswith("v") and path.parent.name == family:
                version = path.name
            _register_catalog_entry(found, family, path, version)
    return found


def _discover_apps_from_scan(root: Path) -> dict[str, Path]:
    """Scan ``apps/<name>/v*`` → ``name@version``. Bare ``apps/<name>`` stays ``name``."""
    found: dict[str, Path] = {}
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return found
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        if _is_app_directory(app_dir):
            _register_catalog_entry(found, app_dir.name, app_dir, None)
            continue
        for ver_dir in _version_dirs(app_dir):
            _register_catalog_entry(found, app_dir.name, ver_dir, ver_dir.name)
    return found


@lru_cache(maxsize=None)
def apps_in_library(root: Path) -> dict[str, Path]:
    """Catalog ids → app directories for one library root (explicit versions only)."""
    manifest = _load_library_manifest(root)
    found = _discover_apps_from_manifest(root, manifest)
    for name, path in _discover_apps_from_scan(root).items():
        found.setdefault(name, path)
    return found


def discover_apps() -> dict[str, Path]:
    """Resolve apps from ``library.yaml`` first, then ``apps/<name>/v*`` scan.

    Bare ``name`` aliases the highest ``name@version``. Later library roots
    do not overwrite an earlier id.
    """
    found: dict[str, Path] = {}
    for root in discover_library_roots():
        for name, path in _add_latest_aliases(apps_in_library(root)).items():
            found.setdefault(name, path)
    return found


@lru_cache(maxsize=None)
def _index_apps(root: Path) -> dict[str, Path]:
    return _add_latest_aliases(apps_in_library(root))


@lru_cache(maxsize=None)
def _index_datasets(root: Path) -> dict[str, Path]:
    manifest = _load_library_manifest(root)
    found = _discover_datasets_from_manifest(root, manifest)
    for name, path in _discover_datasets_from_scan(root).items():
        found.setdefault(name, path)
    return _add_latest_aliases(found)


def resolve_id_in_library(
    root: Path,
    object_id: str,
    *,
    kind: str | None = None,
) -> Path | None:
    """Resolve a catalog id inside one library root.

    *kind* is ``app`` (directory), ``dataset`` (file), or ``None`` (app, then
    dataset). Ids use ``name`` (latest) or ``name@version``. Slash is a path,
    not an id alias.
    """
    if kind in (None, "app"):
        path = _lookup_versioned(_index_apps(root), object_id)
        if path is not None:
            return path
    if kind in (None, "dataset"):
        path = _lookup_versioned(_index_datasets(root), object_id)
        if path is not None:
            return path
    return None


def resolve_catalog_id(
    object_id: str,
    *,
    kind: str | None = None,
    library: str | None = None,
) -> Path | None:
    """Resolve ``name`` / ``name@version`` across libraries, or in one named library."""
    if library:
        from mas.library_roots import resolve_named_library_root

        root = resolve_named_library_root(library)
        if root is None:
            return None
        return resolve_id_in_library(root, object_id, kind=kind)
    for root in discover_library_roots():
        path = resolve_id_in_library(root, object_id, kind=kind)
        if path is not None:
            return path
    return None


def resolve_library_app(scheme: str, app_id: str) -> Path | None:
    """Resolve ``scheme:app_id`` to an application directory."""
    from mas.library_roots import resolve_named_library_root

    root = resolve_named_library_root(scheme)
    if root is None:
        return None
    return resolve_id_in_library(root, app_id, kind="app")


def app_manifest_file(app_root: Path) -> Path | None:
    """Return ``mas.yaml`` / ``mas-bench.yaml`` under an app directory."""
    for name in ("mas.yaml", "mas-bench.yaml"):
        candidate = app_root / name
        if candidate.is_file():
            return candidate
    return None


def _looks_like_dataset(path: Path) -> bool:
    """True for ``kind: Dataset`` (or a legacy untyped dataset YAML)."""
    try:
        data = load_yaml_file(path)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    kind = data.get("kind")
    if kind == "Dataset":
        return True
    if kind:
        return False
    return "items" in data or "spec" in data or "metadata" in data


def _dataset_file_in_dir(path: Path) -> Path | None:
    if not path.is_dir():
        return None
    preferred = path / "dataset.yaml"
    if preferred.is_file() and _looks_like_dataset(preferred):
        return preferred.resolve()
    matches = [
        candidate.resolve()
        for candidate in sorted(path.glob("*.yaml"))
        if _looks_like_dataset(candidate)
    ]
    if not matches:
        return None
    return matches[0]


def _index_dataset_family(found: dict[str, Path], name: str, path: Path, key_ver: str | None) -> None:
    versions = [
        child for child in _version_named_dirs(path) if _dataset_file_in_dir(child) is not None
    ]
    if versions:
        family = name or path.name
        for ver_dir in versions:
            dataset = _dataset_file_in_dir(ver_dir)
            if dataset is not None:
                _register_catalog_entry(found, family, dataset, ver_dir.name)
        return
    dataset = path if path.is_file() else _dataset_file_in_dir(path)
    if dataset is not None:
        _register_catalog_entry(found, name or path.stem, dataset, key_ver)


def _discover_datasets_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict):
        return found

    for name, rel in datasets.items():
        if not isinstance(name, str):
            continue
        path = _resolve_manifest_entry(root, rel)
        if path is None:
            continue
        key_name, key_ver = parse_versioned_id(name)
        family = key_name or name
        if path.is_file():
            _register_catalog_entry(found, family, path, key_ver)
            if key_ver:
                found.setdefault(name, path.resolve())
            continue
        _index_dataset_family(found, family, path, key_ver)
    return found


def _scan_generic_datasets(root: Path, found: dict[str, Path]) -> None:
    datasets_dir = root / "datasets"
    if not datasets_dir.is_dir():
        return
    for path in sorted(datasets_dir.rglob("*.yaml")):
        if not _looks_like_dataset(path):
            continue
        resolved = path.resolve()
        for key in _dataset_keys(path, datasets_dir):
            found.setdefault(key, resolved)


def _family_name_from_dataset_dir(path: Path) -> str:
    dataset = _dataset_file_in_dir(path)
    if dataset is None:
        return path.name
    try:
        data = load_yaml_file(dataset)
    except Exception:
        return path.name
    if not isinstance(data, dict):
        return path.name
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    name = meta.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return path.name


def _scan_one_datasets_dir(
    datasets_dir: Path, found: dict[str, Path], default_version: str | None
) -> None:
    if not datasets_dir.is_dir():
        return
    for child in sorted(datasets_dir.iterdir()):
        if child.suffix in {".yaml", ".yml"} and child.is_file() and _looks_like_dataset(child):
            _register_catalog_entry(found, child.stem, child, default_version)
            continue
        if not child.is_dir():
            continue
        if child.name in {"fixtures", "incidents"} and _dataset_file_in_dir(child) is None:
            # Overlay scene YAML, not a Dataset — unless it has v* Dataset dirs.
            if not any(_dataset_file_in_dir(v) for v in _version_named_dirs(child)):
                continue
        _index_dataset_family(
            found, _family_name_from_dataset_dir(child), child, default_version
        )


def _scan_app_datasets(root: Path, found: dict[str, Path]) -> None:
    """App-specific datasets live at ``apps/<app>/v<N>/datasets/<name>/``.

    Genuinely unversioned apps (no ``v*`` folders at all) keep scanning
    ``apps/<app>/datasets/<name>/`` instead — unchanged from before. For an
    app that does have its own ``v*`` version folders, only the version
    folders are scanned: the family-level ``apps/<app>/datasets/`` fallback
    no longer also runs for it, so the older sibling layout
    ``apps/<app>/datasets/<name>/v<N>/`` no longer indexes for a versioned
    app (it was always redundant there, since the same dataset already
    indexes under its ``v<N>/datasets/<name>/`` location).
    """
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        version_dirs = _version_named_dirs(app_dir)
        for ver_dir in version_dirs:
            _scan_one_datasets_dir(ver_dir / "datasets", found, ver_dir.name)
        if not version_dirs:
            _scan_one_datasets_dir(app_dir / "datasets", found, None)


def _discover_datasets_from_scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    _scan_generic_datasets(root, found)
    _scan_app_datasets(root, found)
    return found


def discover_datasets() -> dict[str, Path]:
    """Resolve datasets from ``library.yaml``, then generic ``datasets/`` and app version folders."""
    found: dict[str, Path] = {}
    for root in discover_library_roots():
        for name, path in _index_datasets(root).items():
            found.setdefault(name, path)
    return found


def catalog_id_for_app_root(app_root: Path) -> str:
    """``sre-triage@v2`` for ``apps/sre-triage/v2``, else the directory name."""
    if app_root.name.startswith("v"):
        return versioned_id(app_root.parent.name, app_root.name)
    return app_root.name


def ensure_dataset_supports_app(dataset_path: Path, app_root: Path) -> None:
    """Raise ``ValueError`` when an app-specific dataset does not declare this app."""
    try:
        data = load_yaml_file(dataset_path)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    spec = data.get("spec") if isinstance(data.get("spec"), dict) else {}
    raw = spec.get("app")
    if raw is None:
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        raw = meta.get("app")
    if raw is None:
        return
    app_id = catalog_id_for_app_root(app_root)
    dep = parse_app_dependency(raw)
    if dep is None:
        return
    if app_satisfies(app_id, dep):
        return
    logger.warning(
        "Dataset %s declares spec.app: %s, which does not include app %s; loading anyway",
        dataset_path,
        dep,
        app_id,
    )


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
            candidates.append((root / LIBRARY_MANIFEST_FILENAME).resolve())
        candidates.extend(_discover_plugin_manifests_from_catalog(root, manifest))
        candidates.extend(_discover_plugin_manifests_from_scan(root))
        for path in candidates:
            if path not in seen:
                seen.add(path)
                found.append(path)
    return found


def clear_catalog_discovery_cache() -> None:
    """Drop memoized ``library.yaml`` parses and app/dataset indices.

    :func:`_load_library_manifest`, :func:`apps_in_library`, :func:`_index_apps`,
    and :func:`_index_datasets` are ``lru_cache``-memoized by resolved library
    root since they re-walk the filesystem on every call otherwise, and this
    is reachable from the per-dataset-item ``{ref:}`` resolution path. Call
    this after a library's on-disk contents change (e.g. a temp library
    directory rewritten mid-test) so the next resolution re-reads them.
    """
    _load_library_manifest.cache_clear()
    apps_in_library.cache_clear()
    _index_apps.cache_clear()
    _index_datasets.cache_clear()
