#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Manifest version constants and helpers."""

from pathlib import Path
from typing import Any, Dict, Union

#: The manifest format shipped with this release of mas-lab.
CURRENT_VERSION: str = "v1"

#: Version assumed when the manifest carries no ``version:`` field.
DEFAULT_VERSION: str = "v1"


def is_rc(version: str) -> bool:
    """Return ``True`` if *version* is a release-candidate (e.g. ``'v1-rc0'``)."""
    return "-rc" in version


def detect_version(raw: Dict[str, Any]) -> str:
    """Return the version string declared in *raw* YAML data."""
    for top_key in ("experiment", "pipeline", "lab"):
        top = raw.get(top_key)
        if isinstance(top, dict) and "version" in top:
            return str(top["version"])
    if "version" in raw:
        return str(raw["version"])
    return DEFAULT_VERSION


def strip_rc(version: str) -> str:
    """Return the base version without any RC suffix (``'v1-rc0'`` → ``'v1'``)."""
    return version.split("-rc")[0]


def assert_supported(version: str, path: Union[str, Path]) -> None:
    """Raise :class:`ValueError` when *version* is not the current format."""
    if version == CURRENT_VERSION:
        return
    if is_rc(version):
        raise ValueError(
            f"Manifest '{path}' uses RC version '{version}' which is not "
            f"supported. Only '{CURRENT_VERSION}' is valid in this release."
        )
    raise ValueError(
        f"Manifest '{path}' uses format version '{version}' which is not "
        f"supported. Upgrade the manifest to '{CURRENT_VERSION}'."
    )
