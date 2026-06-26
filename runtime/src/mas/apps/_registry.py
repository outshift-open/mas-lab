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
    apps = _discover_apps()
    if name not in apps:
        available = ", ".join(sorted(apps)) or "(none found)"
        raise AppNotFoundError(
            f"App '{name}' not found. Available: {available}. "
            "Declare the app under manifest_libraries in mas-workspace.yaml "
            "or register a mas.apps entry point."
        )
    return apps[name]


def list_apps() -> list[str]:
    return sorted(_discover_apps())
