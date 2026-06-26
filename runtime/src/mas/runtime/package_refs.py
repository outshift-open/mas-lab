#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Helpers for resolving package-backed resource references."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
from pathlib import Path


def _manifest_library_root(scheme: str) -> Path | None:
    """Root path for a ``mas.runtime.manifest_libraries`` entry-point scheme."""
    try:
        from mas.library_roots import resolve_manifest_library_package

        eps = importlib.metadata.entry_points(group="mas.runtime.manifest_libraries")
    except Exception:
        return None
    for ep in eps:
        if ep.name == scheme:
            root = resolve_manifest_library_package(ep.value)
            if root is not None:
                return root
    return None


def resolve_library_scheme_root(scheme: str) -> Path | None:
    """Public helper — resolve a manifest library scheme (e.g. ``samples``)."""
    return _manifest_library_root(scheme)


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
    """Resolve a relative filesystem path or a pkg:// resource reference."""
    if ref.startswith("pkg://"):
        package_path = ref[len("pkg://") :]
        package, sep, resource_rel = package_path.partition("/")
        if not sep:
            raise ValueError(f"Invalid package ref without resource path: {ref}")
        return _resolve_pkg_resource(package, resource_rel)

    if ":" in ref and not ref.startswith("/"):
        scheme, _, rel_path = ref.partition(":")
        if scheme and "/" not in scheme and "\\" not in scheme:
            lib_root = _manifest_library_root(scheme)
            if lib_root is not None:
                return lib_root / rel_path

    p = Path(ref)
    return p if p.is_absolute() else (base_dir / ref).resolve()
