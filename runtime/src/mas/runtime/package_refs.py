#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Helpers for resolving package-backed resource references."""

from __future__ import annotations

import importlib
import importlib.resources
from pathlib import Path

from mas.version_spec import split_library_prefix


def _manifest_library_root(scheme: str, *anchors: Path | None) -> Path | None:
    """On-disk root for library *scheme*, or None if that library is not present."""
    from mas.library_roots import resolve_named_library_root

    return resolve_named_library_root(scheme, *anchors)


def resolve_library_scheme_root(scheme: str, *anchors: Path | None) -> Path | None:
    """Public helper — root of a named manifest library, or None."""
    return _manifest_library_root(scheme, *anchors)


def _ctl_example_package_root(package: str) -> Path | None:
    """Resolve ctl-shipped example apps (editable ``ctl/src/<package>/`` layout)."""
    try:
        import mas.ctl

        src_root = Path(mas.ctl.__file__).resolve().parents[2]
        candidate = src_root / package
        return candidate if candidate.is_dir() else None
    except Exception:
        return None


def _resolve_pkg_resource(package: str, resource_rel: str) -> Path:
    try:
        resource = importlib.resources.files(package)
        for part in resource_rel.split("/"):
            if part:
                resource = resource.joinpath(part)
        return Path(resource)
    except (ModuleNotFoundError, TypeError, ValueError):
        ctl_root = _ctl_example_package_root(package)
        if ctl_root is not None:
            target = (ctl_root / resource_rel).resolve()
            if target.exists():
                return target
        raise ModuleNotFoundError(f"No package resource root for {package!r}") from None


def resolve_path_ref(ref: str, base_dir: Path) -> Path:
    """Resolve a library ref (``name:path``), ``pkg://`` resource, or filesystem path.

    A ``name:path`` string is always a library name. Missing libraries raise
    ``LookupError``; they are not interpreted as relative paths.
    """
    if ref.startswith("pkg://"):
        package_path = ref[len("pkg://") :]
        package, sep, resource_rel = package_path.partition("/")
        if not sep:
            raise ValueError(f"Invalid package ref without resource path: {ref}")
        return _resolve_pkg_resource(package, resource_rel)

    scheme, rel_path = split_library_prefix(ref)
    if scheme is not None:
        lib_root = _manifest_library_root(scheme, base_dir)
        if lib_root is None:
            raise LookupError(f"unknown library {scheme!r}")
        return _resolve_in_library(lib_root, rel_path)

    catalog = _resolve_unqualified_catalog_id(ref)
    if catalog is not None:
        return catalog

    p = Path(ref)
    return p if p.is_absolute() else (base_dir / ref).resolve()


def path_ref_for_anchor(path: Path, anchor: Path) -> str:
    """Express a resolved filesystem path as a manifest ref relative to *anchor*.

    *anchor* is typically the MAS application root (parent of ``mas.yaml``).
    When *path* is not under *anchor*, returns an absolute POSIX path string.
    """
    resolved = path.resolve()
    root = anchor.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_in_library(lib_root: Path, rel_path: str) -> Path:
    """Resolve a manifest-library-relative ref, URN-style.

    The ``.yaml``/``.yml`` extension and a leading ``pipelines/`` are both
    optional, so all of these resolve to the same file::

        telemetry:pipelines/native-to-otel-json.yaml   (explicit)
        telemetry:pipelines/native-to-otel-json         (.yaml implied)
        telemetry:native-to-otel-json                   (pipelines/ + .yaml implied)

    The first candidate that exists wins; if none exist the literal
    ``lib_root / rel_path`` is returned (preserving prior behaviour and letting
    the caller raise a clear not-found error).
    """
    rel = rel_path.lstrip("/")
    candidates = [rel]
    if not rel.endswith((".yaml", ".yml", ".json")):
        candidates += [f"{rel}.yaml", f"{rel}.yml"]
    # Allow omitting the conventional `pipelines/` subdir.
    if not rel.startswith("pipelines/"):
        candidates += [f"pipelines/{c}" for c in list(candidates)]
    for cand in candidates:
        target = lib_root / cand
        if target.exists():
            return target
    catalog = _resolve_library_catalog_rel(lib_root, rel)
    if catalog is not None:
        return catalog
    nested = _resolve_catalog_relative(rel, lib_root=lib_root)
    if nested is not None:
        return nested
    return lib_root / rel


def _looks_like_catalog_id(ref: str) -> bool:
    """True when *ref* is ``name`` or ``name@version``, not a filesystem path.

    Slash is a path. File extensions are paths. ``LIBRARY:`` is handled separately.
    """
    text = str(ref or "").strip()
    if not text or text.startswith((".", "/", "\\")):
        return False
    if "/" in text or "\\" in text:
        return False
    if text.endswith((".yaml", ".yml", ".json")):
        return False
    return True


def _catalog_path_to_ref(path: Path) -> Path:
    from mas.library_catalog import app_manifest_file

    if path.is_dir():
        manifest = app_manifest_file(path)
        return manifest if manifest is not None else path
    return path


def _catalog_dir(path: Path) -> Path:
    """Folder to join a catalog-relative suffix onto (app dir or dataset dir)."""
    return path.parent if path.is_file() else path


def _resolve_catalog_relative(rel: str, *, lib_root: Path | None) -> Path | None:
    """Resolve ``name@version/path`` as a file inside a catalog object.

    ``example-library:example-datasets@v2/tool_fixtures/foo.yaml`` is the
    Dataset folder plus a sibling payload. ``example-library:example-app@v2/tools/…``
    is the app version folder plus a path. Slash after a *folder* name
    (``apps/…``) stays a library-root path; this only fires when the first
    segment is a catalog id.
    """
    text = rel.lstrip("/")
    if "/" not in text:
        return None
    head, rest = text.split("/", 1)
    if not rest or not _looks_like_catalog_id(head):
        return None
    from mas.library_catalog import resolve_catalog_id, resolve_id_in_library

    path = (
        resolve_id_in_library(lib_root, head, kind=None)
        if lib_root is not None
        else resolve_catalog_id(head, kind=None)
    )
    if path is None:
        return None
    anchor = _catalog_dir(path)
    candidates = [rest]
    if not rest.endswith((".yaml", ".yml", ".json")):
        candidates += [f"{rest}.yaml", f"{rest}.yml"]
    for cand in candidates:
        target = anchor / cand
        if target.exists():
            return target
    return anchor / rest


def _resolve_unqualified_catalog_id(ref: str) -> Path | None:
    """Look up a global catalog id before treating *ref* as a relative path."""
    if _looks_like_catalog_id(ref):
        from mas.library_catalog import resolve_catalog_id

        path = resolve_catalog_id(ref, kind=None)
        if path is None:
            return None
        return _catalog_path_to_ref(path)
    return _resolve_catalog_relative(ref, lib_root=None)


def _resolve_library_catalog_rel(lib_root: Path, rel: str) -> Path | None:
    """Resolve a catalog id (app or dataset) when no file path exists under *lib_root*."""
    from mas.library_catalog import resolve_id_in_library

    path = resolve_id_in_library(lib_root, rel, kind=None)
    if path is None:
        return None
    return _catalog_path_to_ref(path)
