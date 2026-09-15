#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""IoC catalog provider abstraction and filesystem implementation."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IocCatalogProvider(ABC):
    """Read-only provider for the IoC challenge catalog.

    Subclass this to swap in a remote catalog source without touching the routes.
    """

    @abstractmethod
    def get_catalog(self) -> dict[str, Any]:
        """Return the full parsed catalog (apps, challenges, overlays, metrics)."""

    @abstractmethod
    def get_overlay_content(self, overlay_id: str) -> dict[str, str]:
        """Return ``{"id": ..., "overlay": ..., "content": ...}`` for a catalog overlay.

        Raises ``KeyError`` if the id is not in the catalog.
        Raises ``FileNotFoundError`` if the overlay file is missing on disk.
        """

    @abstractmethod
    def list_overlay_ids(self) -> dict[str, str]:
        """Return ``{overlay_id: relative_path}`` for every overlay in the catalog."""


class FilesystemCatalogProvider(IocCatalogProvider):
    """Loads the catalog from ``{ioc_repo}/catalog/ioc-catalog.json``.

    Re-reads the file when its mtime changes so edits in ioc-core-mas-lab are
    picked up without restarting the server.
    """

    def __init__(self, ioc_repo: Path) -> None:
        self._ioc_repo = ioc_repo.resolve()
        self._catalog_path = self._ioc_repo / "catalog" / "ioc-catalog.json"
        self._cached_catalog: dict[str, Any] | None = None
        self._cached_mtime: float = 0.0
        self._overlay_index: dict[str, str] | None = None

    def _ensure_loaded(self) -> dict[str, Any]:
        """(Re-)load the catalog if the file has been modified since last read."""
        try:
            current_mtime = self._catalog_path.stat().st_mtime
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"IoC catalog not found at {self._catalog_path}. "
                f"Verify IOC_REPO={self._ioc_repo} points at a valid ioc-core-mas-lab checkout."
            ) from exc

        if self._cached_catalog is None or current_mtime != self._cached_mtime:
            logger.info("Loading IoC catalog from %s", self._catalog_path)
            text = self._catalog_path.read_text(encoding="utf-8")
            self._cached_catalog = json.loads(text)
            self._cached_mtime = current_mtime
            self._overlay_index = None

        return self._cached_catalog  # type: ignore[return-value]

    def _build_overlay_index(self) -> dict[str, str]:
        """Build ``{overlay_id: relative_path}`` from the catalog."""
        if self._overlay_index is not None:
            return self._overlay_index

        catalog = self._ensure_loaded()
        index: dict[str, str] = {}
        for app_data in (catalog.get("apps") or {}).values():
            for challenge in app_data.get("challenges", []):
                for ov in challenge.get("overlays", []):
                    index[ov["id"]] = ov["overlay"]
        self._overlay_index = index
        return index

    def get_catalog(self) -> dict[str, Any]:
        return self._ensure_loaded()

    def list_overlay_ids(self) -> dict[str, str]:
        return dict(self._build_overlay_index())

    def get_overlay_content(self, overlay_id: str) -> dict[str, str]:
        index = self._build_overlay_index()
        if overlay_id not in index:
            raise KeyError(overlay_id)

        relative_path = index[overlay_id]
        resolved = (self._ioc_repo / relative_path).resolve()

        if not str(resolved).startswith(str(self._ioc_repo)):
            raise ValueError(
                f"Path traversal rejected: overlay '{overlay_id}' resolves outside IOC_REPO"
            )

        if not resolved.is_file():
            raise FileNotFoundError(
                f"Overlay file not found: {relative_path} (resolved to {resolved})"
            )

        return {
            "id": overlay_id,
            "overlay": relative_path,
            "content": resolved.read_text(encoding="utf-8"),
        }


_provider: IocCatalogProvider | None = None


def get_ioc_catalog_provider() -> IocCatalogProvider:
    """Return the singleton provider, creating it on first call.

    Raises ``RuntimeError`` if ``IOC_REPO`` is not configured.
    """
    global _provider  # noqa: PLW0603
    if _provider is not None:
        return _provider

    from mas.lab.controller.constants import IOC_REPO

    if IOC_REPO is None:
        raise RuntimeError(
            "IOC_REPO environment variable is not set. "
            "Set it to the absolute path of your ioc-core-mas-lab checkout."
        )
    if not IOC_REPO.is_dir():
        raise RuntimeError(
            f"IOC_REPO={IOC_REPO} does not exist or is not a directory. "
            "Verify the path points at a valid ioc-core-mas-lab checkout."
        )

    _provider = FilesystemCatalogProvider(IOC_REPO)
    return _provider


def set_ioc_catalog_provider(provider: IocCatalogProvider | None) -> None:
    """Override the singleton (for testing)."""
    global _provider  # noqa: PLW0603
    _provider = provider
