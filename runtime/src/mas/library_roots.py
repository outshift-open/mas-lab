#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover manifest library roots from lab, workspace, and installed libraries.

A "manifest library" is a folder with a ``library.yaml`` at its root.
``name:path`` refs always use a library name; unknown names raise
``LookupError`` (they are never a filesystem path). Discovery order is
shared by :func:`resolve_named_library_root` and
:func:`discover_library_roots` so ctl, runtime, and lab cannot drift:

1. **Lab-local** — from the enclosing ``lab-config.yaml`` (see
   :func:`find_lab_dir`): ``lab.libraries`` entries that are directories
   containing ``library.yaml``, plus **immediate** children of the lab
   root that contain ``library.yaml``. The library name is the listed
   basename (``mylib/`` → ``mylib``) or the child directory name. A
   listed directory **without** ``library.yaml`` is Python ``sys.path``
   only (no library name). A listed name that is already a known library
   (``samples``) keeps resolve-by-name behaviour via later steps.
2. **Workspace config** — ``config.yaml`` ``manifest_libraries:``
   (library name → path, relative to the workspace root).
3. **Installed libraries** — libraries registered in the environment.
4. **Known local paths** — ``MAS_LIBRARY_PATHS`` (``os.pathsep``-
   separated): each entry is a library root or a parent of sibling
   library folders. Enumeration hatch; names are directory basenames.
5. **Ancestor walk** — upward from anchors/cwd for ``library.yaml``,
   stopping at ``.git``. Also stops at a ``.lab`` directory so a
   ``library.yaml`` on the lab root is not dual-registered as both the
   lab slug and the directory stem (skipping that lab-root file is
   intentional).

First-seen name wins: a lab-local library shadows an installed library
of the same name. ``.git`` is a walk boundary, not a search root — sibling
``library-*`` checkouts are not scanned.

Every installed-library strategy is defensive: a single library with a
broken import must never prevent *other* libraries from being discovered.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
import importlib.util
import json
import os
from pathlib import Path

import yaml
from mas.runtime.constants import LAB_CONFIG_FILENAME, LIBRARY_MANIFEST_FILENAME

_LAB_DIR_SUFFIX = ".lab"


def find_ancestor_with_file(
    start: Path, filename: str, *, stop_at_suffix: str | None = None
) -> Path | None:
    """Walk upward from *start* to find a directory containing *filename*.

    Checks *start* itself (or its parent, if *start* is a file) first, then
    each ancestor in turn. If *stop_at_suffix* is given, the ancestor whose
    name carries that suffix is still checked (so e.g. a ``.lab`` root is
    itself eligible) but the walk does not continue past it -- this avoids
    picking up an unrelated outer lab's or checkout's marker file.

    Shared by every "find the enclosing root" discovery in this codebase
    (manifest libraries via ``library.yaml``, labs via ``lab-config.yaml``)
    so the walk-and-stop semantics stay in exactly one place.
    """
    here = start if start.is_dir() else start.parent
    for parent in [here, *here.parents]:
        if (parent / filename).is_file():
            return parent.resolve()
        if stop_at_suffix and parent.name.endswith(stop_at_suffix):
            break
    return None


def _find_library_root(start: Path) -> Path | None:
    """Walk upward from *start* to find a directory with ``library.yaml``."""
    return find_ancestor_with_file(start, LIBRARY_MANIFEST_FILENAME)


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


def _installed_named_libraries() -> dict[str, Path]:
    """Return library name → root for installed libraries."""
    named: dict[str, Path] = {}
    try:
        eps = importlib.metadata.entry_points(group="mas.runtime.manifest_libraries")
    except Exception:
        return named

    for ep in eps:
        try:
            dist_name = getattr(getattr(ep, "dist", None), "name", None)
            root = resolve_manifest_library_package(ep.value, dist_name)
        except Exception:
            # Belt-and-suspenders: resolve_manifest_library_package() already
            # guards every strategy it tries, but one broken installed library
            # must never stop the rest of this loop from running.
            continue
        if root is not None and ep.name and ep.name not in named:
            named[ep.name] = root
    return named


def _installed_library_roots() -> list[Path]:
    """Return roots for installed libraries (name order from :func:`_installed_named_libraries`)."""
    return list(_installed_named_libraries().values())


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
        if (base / LIBRARY_MANIFEST_FILENAME).is_file():
            roots.append(base.resolve())
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / LIBRARY_MANIFEST_FILENAME).is_file():
                roots.append(child.resolve())
    return roots


def _scheme_from_listed_entry(entry: str) -> str:
    """Library name for a ``lab.libraries`` path (``mylib/`` → ``mylib``)."""
    return Path(str(entry).rstrip("/\\")).name


def _is_lab_root(path: Path) -> bool:
    """True if *path* is a lab root (``.lab`` suffix or ``lab-config.yaml``)."""
    return path.name.endswith(_LAB_DIR_SUFFIX) or (path / LAB_CONFIG_FILENAME).is_file()


def find_lab_dir(start: Path) -> Path | None:
    """Enclosing lab root from *start*, stopping at a ``.lab`` directory."""
    return find_ancestor_with_file(
        start, LAB_CONFIG_FILENAME, stop_at_suffix=_LAB_DIR_SUFFIX
    )


def _lab_library_entries(lab_dir: Path) -> list[str]:
    """Return ``lab.libraries`` path entries from ``lab-config.yaml``."""
    cfg = lab_dir / LAB_CONFIG_FILENAME
    if not cfg.is_file():
        return []
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    section = data.get("lab", data)
    if not isinstance(section, dict):
        return []
    raw = section.get("libraries") or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if x]


def _lab_local_named_libraries(lab_dir: Path) -> dict[str, Path]:
    """Lab-local library name → root (listed ``library.yaml`` dirs + immediate children)."""
    named: dict[str, Path] = {}

    def _add(scheme: str, path: Path) -> None:
        name = scheme.strip()
        if not name or name in named:
            return
        if path.is_dir() and (path / LIBRARY_MANIFEST_FILENAME).is_file():
            named[name] = path.resolve()

    for entry in _lab_library_entries(lab_dir):
        raw = Path(entry).expanduser()
        candidate = raw if raw.is_absolute() else (lab_dir / entry)
        if candidate.is_dir() and (candidate / LIBRARY_MANIFEST_FILENAME).is_file():
            _add(_scheme_from_listed_entry(entry), candidate)

    try:
        children = sorted(lab_dir.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.is_dir() and (child / LIBRARY_MANIFEST_FILENAME).is_file():
            _add(child.name, child)

    return named


def _workspace_named_libraries() -> dict[str, Path]:
    """Workspace ``manifest_libraries:`` name → root."""
    named: dict[str, Path] = {}
    from mas.runtime.workspace_config import RuntimeWorkspaceConfig

    ws = RuntimeWorkspaceConfig.load()
    if ws.found and ws.root is not None:
        for scheme, rel in ws.manifest_libraries.items():
            if isinstance(rel, str) and rel.strip():
                path = Path(rel).expanduser()
                root = path if path.is_absolute() else (ws.root / rel)
                resolved = root.resolve()
                if resolved.exists():
                    named[str(scheme)] = resolved
    return named


def _env_named_libraries() -> dict[str, Path]:
    """``MAS_LIBRARY_PATHS`` roots keyed by directory name."""
    named: dict[str, Path] = {}
    for root in _known_library_paths():
        if root.name and root.name not in named:
            named[root.name] = root
    return named


def _ancestor_named_libraries(*anchors: Path | None) -> dict[str, Path]:
    """Upward ``library.yaml`` walk. Stops at ``.git`` and ``.lab``; skips lab-root files."""
    named: dict[str, Path] = {}
    starts = [a for a in anchors if a is not None]
    if not starts:
        starts = [Path.cwd()]
    for anchor in starts:
        try:
            here = Path(anchor).resolve()
        except Exception:
            continue
        if not here.is_dir():
            here = here.parent
        for parent in (here, *here.parents):
            if (parent / LIBRARY_MANIFEST_FILENAME).is_file() and not _is_lab_root(parent):
                if parent.name and parent.name not in named:
                    named[parent.name] = parent.resolve()
            # .git is a walk boundary. Also stop at .lab so a library.yaml on
            # the lab root is not dual-registered as both the lab slug and
            # the directory stem — skipping that lab-root file is intentional.
            if (parent / ".git").is_dir() or parent.name.endswith(_LAB_DIR_SUFFIX):
                break
    return named


def _search_starts(*anchors: Path | None) -> list[Path]:
    """Anchor paths plus cwd, skipping ``None``."""
    starts: list[Path] = []
    seen: set[Path] = set()
    raw: list[Path | None] = list(anchors) if anchors else []
    raw.append(Path.cwd())
    for anchor in raw:
        if anchor is None:
            continue
        try:
            resolved = Path(anchor).resolve()
        except Exception:
            continue
        if resolved not in seen:
            seen.add(resolved)
            starts.append(resolved)
    return starts


def iter_named_library_roots(*anchors: Path | None) -> list[tuple[str, Path]]:
    """Ordered ``(library name, root)`` pairs. First-seen name wins.

    Used by :func:`resolve_named_library_root` (``name:path``) and
    :func:`discover_library_roots` so ctl, runtime, and lab share one order:
    lab-local, workspace config, installed libraries, ``MAS_LIBRARY_PATHS``,
    ancestor walk.
    """
    ordered: list[tuple[str, Path]] = []
    seen_names: set[str] = set()

    def _merge(mapping: dict[str, Path]) -> None:
        for name, root in mapping.items():
            if not name or name in seen_names:
                continue
            try:
                resolved = root.resolve()
            except Exception:
                continue
            if not resolved.exists():
                continue
            seen_names.add(name)
            ordered.append((name, resolved))

    seen_labs: set[Path] = set()
    for start in _search_starts(*anchors):
        lab_dir = find_lab_dir(start)
        if lab_dir is not None and lab_dir not in seen_labs:
            seen_labs.add(lab_dir)
            _merge(_lab_local_named_libraries(lab_dir))

    _merge(_workspace_named_libraries())
    _merge(_installed_named_libraries())
    _merge(_env_named_libraries())
    _merge(_ancestor_named_libraries(*_search_starts(*anchors)))
    return ordered


def resolve_named_library_root(scheme: str, *anchors: Path | None) -> Path | None:
    """On-disk root for library *scheme*, or ``None`` if that name is unknown."""
    for name, root in iter_named_library_roots(*anchors):
        if name == scheme:
            return root
    return None


def discover_library_roots(*anchors: Path | None) -> list[Path]:
    """Return library roots in the same order as :func:`iter_named_library_roots`.

    ``MAS_LIBRARY_PATHS`` is also applied as an enumeration hatch so a path
    whose directory name collides with an earlier library name is still listed.
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        resolved = path.resolve()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)

    for _name, path in iter_named_library_roots(*anchors):
        _add(path)

    for path in _known_library_paths():
        _add(path)

    return roots
