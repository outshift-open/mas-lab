#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover manifest library roots from installed packages and workspace paths.

A "manifest library" is a folder with a ``library.yaml`` at its root. It is
discovered in one of four ways, all additive:

1. **Installed packages** — a package registers a
   ``mas.runtime.manifest_libraries`` entry point; its on-disk root is
   resolved without requiring a successful full import (see
   :func:`resolve_manifest_library_package`).
2. **Workspace config** — ``config.yaml``'s ``manifest_libraries:`` map
   (scheme -> path, relative to the workspace root).
3. **Known local paths** — the ``MAS_LIBRARY_PATHS`` environment variable
   (``os.pathsep``-separated), for libraries that are not installed as
   packages at all: a plain folder on disk with a ``library.yaml``. Each
   entry may itself be a library root, or a parent directory containing
   several sibling library folders (e.g. a monorepo checkout root).
4. **Anchor scan** — walking upward from a given anchor path (default:
   the current working directory) looking for ``library.yaml``, stopping
   at the first ``.git`` boundary. This is dev-checkout convenience, not
   a substitute for (1)-(3) in an installed environment.

Every resolution strategy here is defensive: a single library with a
broken import (missing optional dependency, stale module reference, etc.)
must never prevent *other* libraries from being discovered. See
:func:`resolve_manifest_library_package`'s docstring for why this matters.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
import importlib.util
import json
import os
from pathlib import Path


def _find_library_root(start: Path) -> Path | None:
    """Walk upward from *start* to find a directory with ``library.yaml``."""
    here = start if start.is_dir() else start.parent
    for parent in [here, *here.parents]:
        if (parent / "library.yaml").is_file():
            return parent.resolve()
    return None


def _root_from_spec(module: str) -> Path | None:
    """Resolve *module*'s on-disk root via :func:`importlib.util.find_spec`.

    ``find_spec`` locates a module without executing its body -- unlike
    :func:`importlib.import_module`, it can't fail because the *target*
    module raises on import. It can still raise, though: per the stdlib
    docs, resolving a dotted submodule spec "automatically imports" its
    parent packages, and a parent package that raises on import propagates
    straight out of ``find_spec`` (reproduced directly: a parent package
    with a broken ``__init__.py`` makes ``find_spec("parent.child")``
    raise ``ImportError``, not return ``None``). Callers must not assume
    this function is side-effect-free or exception-free -- it is
    deliberately wrapped in ``try/except`` here so a single misbehaving
    library can't take down discovery for every other one.
    """
    try:
        spec = importlib.util.find_spec(module)
    except Exception:
        return None
    if spec is not None and spec.origin:
        return _find_library_root(Path(spec.origin).resolve())
    return None


def _root_from_import(module: str) -> Path | None:
    """Resolve *module*'s on-disk root via a full :func:`importlib.import_module`.

    Fallback for modules :func:`_root_from_spec` can't resolve (e.g. a
    namespace package with no ``origin``, or a module exposing a
    ``package_root()`` helper instead of a conventional ``__file__``).
    Guarded the same way: any failure here just means this strategy
    didn't work, not that discovery as a whole should fail.
    """
    try:
        mod = importlib.import_module(module)
    except Exception:
        return None
    root_fn = getattr(mod, "package_root", None)
    if callable(root_fn):
        try:
            return Path(root_fn()).resolve()
        except Exception:
            return None
    mod_file = getattr(mod, "__file__", None)
    if mod_file:
        return _find_library_root(Path(mod_file).resolve())
    return None


def _root_from_editable_distribution(module: str, dist_name: str | None = None) -> Path | None:
    """Resolve *module*'s on-disk root via its distribution's ``direct_url.json``.

    Works for any editable (``pip install -e``) install, not just a fixed
    allowlist of known module names -- ``importlib.metadata.
    packages_distributions()`` maps top-level import names to the
    distribution(s) that provide them, so this generalizes to any library
    package without a code change per library.
    """
    try:
        dist_name = dist_name or next(
            iter(importlib.metadata.packages_distributions().get(module) or []),
            None,
        )
        if not dist_name:
            return None
        dist = importlib.metadata.distribution(dist_name)
        data = json.loads(dist.read_text("direct_url.json"))
        url = data.get("url", "")
        if url.startswith("file://"):
            return _find_library_root(Path(url[7:]))
    except Exception:
        return None
    return None


def resolve_manifest_library_package(module: str, dist_name: str | None = None) -> Path | None:
    """Resolve the on-disk root for a ``mas.runtime.manifest_libraries`` package.

    Tries, in order, until one succeeds: an unexecuted spec lookup, a full
    import, and the owning distribution's recorded editable-install path.
    Every strategy independently swallows its own failures -- this
    function itself never raises, so one library with a broken/missing
    optional dependency never prevents the *rest* of the libraries from
    being discovered (see :func:`_installed_library_roots`).
    """
    found = _root_from_spec(module)
    if found is not None:
        return found

    found = _root_from_import(module)
    if found is not None:
        return found

    found = _root_from_editable_distribution(module, dist_name)
    if found is not None:
        return found

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
        try:
            dist_name = getattr(getattr(ep, "dist", None), "name", None)
            root = resolve_manifest_library_package(ep.value, dist_name)
        except Exception:
            # Belt-and-suspenders: resolve_manifest_library_package() already
            # guards every strategy it tries, but one broken entry point
            # must never stop the rest of this loop from running.
            continue
        if root is not None:
            roots.append(root)
    return roots


def _known_library_paths() -> list[Path]:
    """Return roots from the ``MAS_LIBRARY_PATHS`` environment variable.

    For libraries that are not installed as Python packages at all --
    just a folder with a ``library.yaml`` on disk. Each ``os.pathsep``
    -separated entry is either a library root itself, or a parent
    directory containing one or more sibling library folders (e.g.
    pointing at a monorepo checkout root that has ``library-a/``,
    ``library-b/``, ... as immediate subdirectories).
    """
    raw = os.environ.get("MAS_LIBRARY_PATHS", "")
    roots: list[Path] = []
    for entry in raw.split(os.pathsep):
        entry = entry.strip()
        if not entry:
            continue
        base = Path(entry).expanduser()
        if not base.is_dir():
            continue
        if (base / "library.yaml").is_file():
            roots.append(base.resolve())
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "library.yaml").is_file():
                roots.append(child.resolve())
    return roots


def discover_library_roots(*anchors: Path | None) -> list[Path]:
    """Return library roots from packages, workspace config, known paths, and anchors."""
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

    for path in _known_library_paths():
        _add(path)

    anchor_candidates = anchors or (Path.cwd(),)

    for anchor in anchor_candidates:
        if anchor is None:
            continue
        here = anchor.resolve()
        if not here.is_dir():
            here = here.parent
        for parent in (here, *here.parents):
            if (parent / "library.yaml").is_file():
                _add(parent)
            samples = parent / "library-samples"
            if (samples / "library.yaml").is_file():
                _add(samples)
            if (parent / ".git").is_dir():
                break

    return roots
