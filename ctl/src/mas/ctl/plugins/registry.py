#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ctl plugin resolution — delegates to the runtime URN registry."""

from __future__ import annotations

from typing import Any, Callable


def resolve_callable(urn: str) -> Callable[..., Any] | None:
    """Resolve plugin URN to a class constructor (runtime registry)."""
    from mas.runtime.registry import get_registry

    info = get_registry().resolve(urn)
    if info is None:
        return None
    cls = info.load_class()
    return cls


def create_plugin(urn: str, **kwargs: Any) -> Any:
    factory = resolve_callable(urn)
    if factory is None:
        raise KeyError(f"unknown plugin URN: {urn}")
    try:
        return factory(**kwargs)
    except TypeError:
        return factory()
