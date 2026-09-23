#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Bind advertised tool semantics onto a call.

Libraries declare interpretation on ``list_tools()`` / ``spec.semantics``
(``concept``, ``op``, ``subject_arg``). The kernel copies that dict and
binds ``subject`` from the call arguments. It does not infer meaning from
the tool name.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "advertised_semantics_for",
    "bind_tool_semantics",
    "bound_tool_semantics",
    "existing_attr",
]


def existing_attr(obj: Any, name: str) -> Any:
    """Read ``name`` without ``__getattr__`` (MagicMock would auto-create it)."""
    if obj is None:
        return None
    try:
        return object.__getattribute__(obj, name)
    except AttributeError:
        return None


def bind_tool_semantics(
    advertised: dict[str, Any] | None,
    arguments: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve advertised semantics against this call's arguments.

    Returns ``{concept, op?, subject?}`` or ``None`` when the tool did not
    advertise a concept. ``op`` is copied when set. ``subject`` is the first
    non-empty string among ``subject_arg`` keys (a name or a list of names).
    """
    if not isinstance(advertised, dict):
        return None
    concept = str(advertised.get("concept") or "").strip()
    if not concept:
        return None
    bound: dict[str, Any] = {"concept": concept}
    op = str(advertised.get("op") or "").strip()
    if op:
        bound["op"] = op
    keys = advertised.get("subject_arg")
    if isinstance(keys, str):
        keys = [keys]
    if not isinstance(keys, list):
        keys = []
    args = arguments or {}
    for key in keys:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            bound["subject"] = val.strip()
            break
    return bound


def advertised_semantics_for(
    engine: Any,
    tool_name: str | None,
    *,
    ctx: Any = None,
) -> dict[str, Any] | None:
    """Look up ``semantics`` from the engine's advertised tool list."""
    if not tool_name or engine is None:
        return None
    provider = existing_attr(engine, "tool_provider")
    if provider is None:
        return None
    list_fn = existing_attr(provider, "list_tools")
    if not callable(list_fn):
        return None
    lookup_ctx = ctx if ctx is not None else existing_attr(engine, "ctx")
    try:
        specs = list_fn(ctx=lookup_ctx)
    except TypeError:
        try:
            specs = list_fn()
        except Exception:
            return None
    except Exception:
        return None
    if not isinstance(specs, (list, tuple)):
        return None
    for spec in specs:
        if not isinstance(spec, dict) or spec.get("name") != tool_name:
            continue
        raw = spec.get("semantics")
        return dict(raw) if isinstance(raw, dict) else None
    return None


def bound_tool_semantics(
    engine: Any,
    tool_name: str | None,
    arguments: dict[str, Any] | None,
    *,
    ctx: Any = None,
) -> dict[str, Any] | None:
    """Advertised semantics for ``tool_name``, bound to this call."""
    return bind_tool_semantics(
        advertised_semantics_for(engine, tool_name, ctx=ctx),
        arguments,
    )
