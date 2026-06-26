#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Normalize overlay documents to mas/v1 kind: Overlay before validate/merge."""

from __future__ import annotations

from typing import Any


def normalize_overlay(data: dict[str, Any], *, name: str = "overlay") -> dict[str, Any]:
    """Require canonical ``mas/v1`` ``Overlay`` with ``spec.patch`` (dict)."""
    if not isinstance(data, dict):
        raise ValueError("overlay must be a mapping")

    api = str(data.get("apiVersion") or "")
    kind = str(data.get("kind") or "")
    if api != "mas/v1" or kind != "Overlay":
        raise ValueError(
            f"unsupported overlay shape (apiVersion={api!r}, kind={kind!r}); "
            "use mas/v1 kind: Overlay with spec.patch"
        )

    spec = data.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("Overlay spec must be a mapping")
    patch = spec.get("patch")
    if not isinstance(patch, dict):
        raise ValueError("Overlay spec.patch is required and must be a mapping")

    return dict(data)
