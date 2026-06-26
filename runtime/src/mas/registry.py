#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.registry — unified object factory for MAS manifest libraries."""

from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path
from typing import Optional, Union

from mas.library_catalog import discover_apps, discover_datasets, discover_tools

logger = logging.getLogger(__name__)


class NotFoundError(KeyError):
    """Raised when a named object is not found in the registry."""


_CATALOG = {
    "app": discover_apps,
    "dataset": discover_datasets,
    "tool": discover_tools,
}


def _ep_group(kind: str) -> str:
    return f"mas.{kind}s"


def _discover(kind: str) -> dict[str, Path]:
    """Merge library catalog with ``mas.<kind>s`` entry points (EPs win)."""
    result = _CATALOG[kind]()
    for ep in importlib.metadata.entry_points(group=_ep_group(kind)):
        try:
            fn = ep.load()
            path = fn() if callable(fn) else Path(str(fn))
            if path.exists():
                result[ep.name] = path
        except Exception:
            logger.warning("Failed to load %s entry point %r; skipping.", kind, ep.name, exc_info=True)
    return result


def get(kind: str, name: str) -> Path:
    objects = _discover(kind)
    if name not in objects:
        available = ", ".join(sorted(objects)) or f"(no {kind}s found)"
        raise NotFoundError(
            f"{kind.capitalize()} '{name}' not found in registry. "
            f"Available: {available}."
        )
    return objects[name]


def list_names(kind: str) -> list[str]:
    return sorted(_discover(kind))


def resolve_locator(
    locator: Union[str, dict],
    kind: str,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    if isinstance(locator, str):
        return get(kind, locator)

    if "path" in locator:
        p = Path(locator["path"])
        if not p.is_absolute() and base_dir is not None:
            p = (base_dir / p).resolve()
        return p

    if "app" in locator:
        app_root = get("app", locator["app"])
        if kind == "app":
            return app_root
        name = locator.get("name", kind)
        return (app_root / f"{kind}s" / f"{name}.yaml").resolve()

    if "name" in locator:
        name = locator["name"]
        try:
            return get(kind, name)
        except NotFoundError:
            if base_dir is not None:
                candidate = base_dir / f"{kind}s" / f"{name}.yaml"
                if candidate.exists():
                    return candidate.resolve()
            raise

    raise ValueError(
        f"Cannot resolve {kind} from locator {locator!r}. "
        "Expected one of: 'path', 'app', or 'name'."
    )
