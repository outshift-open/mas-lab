#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""App registry — discover apps via library catalog and entry points."""

from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path
from typing import Callable

from mas.library_catalog import discover_apps

logger = logging.getLogger(__name__)


class AppNotFoundError(KeyError):
    """Raised when a named app is not registered."""


def _discover_apps() -> dict[str, Path]:
    apps = discover_apps()
    for ep in importlib.metadata.entry_points(group="mas.apps"):
        try:
            fn: Callable[[], Path] = ep.load()
            path = fn() if callable(fn) else Path(str(fn))
            if path.exists():
                apps[ep.name] = path
        except Exception:
            logger.warning("Failed to load app entry point %r; skipping.", ep.name, exc_info=True)
    return apps


def get_app(name: str) -> Path:
    """Return the application directory for a catalog id or ``library:app`` ref.

    Canonical id: ``[library:]name[@version]`` (``example-library:example-app@v2``).
    Bare ``name`` is ``@latest``. Slash is a filesystem path, not an id alias.
    """
    requested = str(name).strip()
    from mas.library_catalog import parse_library_ref, parse_versioned_id, versioned_id

    parsed = parse_library_ref(requested)
    if parsed is not None:
        scheme, app_id = parsed
        from mas.library_catalog import resolve_library_app

        path = resolve_library_app(scheme, app_id)
        if path is not None:
            return path
        raise AppNotFoundError(
            f"App '{requested}' not found in library {scheme!r}. "
            "Check library.yaml apps: and workspace manifest_libraries."
        )

    apps = _discover_apps()
    if requested in apps:
        return apps[requested]
    name_part, ver = parse_versioned_id(requested)
    if ver:
        keyed = versioned_id(name_part, ver)
        if keyed in apps:
            return apps[keyed]
    elif name_part in apps:
        return apps[name_part]
    available = ", ".join(sorted(apps)) or "(none found)"
    raise AppNotFoundError(
        f"App '{requested}' not found. Available: {available}. "
        "Use library:app (e.g. example-library:example-app@v2) or declare the app "
        "under manifest_libraries in config.yaml."
    )


def resolve_app_manifest(app_root: Path, app_id: str | None = None) -> Path:
    """Resolve the primary manifest for an app directory (MAS or standalone agent)."""
    root = Path(app_root)
    for name in ("mas.yaml", "mas-bench.yaml"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    agents_dir = root / "agents"
    if app_id:
        agent_path = agents_dir / f"{app_id}.yaml"
        if agent_path.is_file():
            return agent_path
    if agents_dir.is_dir():
        agent_yamls = sorted(agents_dir.glob("*.yaml"))
        if app_id:
            for path in agent_yamls:
                if path.stem == app_id:
                    return path
        if len(agent_yamls) == 1:
            return agent_yamls[0]
    for name in ("agent.yaml", f"{root.name}.yaml"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise AppNotFoundError(f"No manifest found under app root {root}")


def list_apps() -> list[str]:
    return sorted(_discover_apps())
