#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Helpers for resolving package-backed resource references."""

from __future__ import annotations

import importlib
import importlib.resources
from pathlib import Path


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

    if ":" in ref and not ref.startswith("/"):
        scheme, _, rel_path = ref.partition(":")
        if scheme and "/" not in scheme and "\\" not in scheme:
            lib_root = _manifest_library_root(scheme, base_dir)
            if lib_root is None:
                raise LookupError(f"unknown library {scheme!r}")
            return _resolve_in_library(lib_root, rel_path)

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
    return lib_root / rel
