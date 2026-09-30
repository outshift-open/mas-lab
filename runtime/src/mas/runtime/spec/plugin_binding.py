#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Cardinality-one plugin slots: string shorthand or {type, ref, params}.

Singleton spec keys (``design_pattern``, ``context_manager``, ``assembler``)
accept either a plugin name or an object. List slots (``governance``,
``observability``) use ``[{plugin_name: {params}}]`` instead — see
``docs/manifests/plugin-bindings.md``.

Two ways to read a binding, for two different callers:

- ``normalize_plugin_binding`` (strict) — the authoring boundary. ``ctl``
  uses this at ``compile``/``validate`` time so a malformed binding is a
  loud, one-time error at authoring, not a surprise later.
- ``normalize_plugin_binding_lenient`` — the runtime hot path. The kernel
  reads an already-authored manifest on every turn (and, in tests or a
  direct embedding, one that never went through ``ctl`` at all); it must
  always produce *some* sane, default behavior rather than turning one bad
  field into a per-turn failure. Runtime call sites that read a manifest
  binding to construct or configure a plugin use the lenient form; ``ctl``
  call sites use the strict form.
"""

from __future__ import annotations

from typing import Any


class PluginBindingError(ValueError):
    """Singleton plugin slot is neither a name nor a {type, ref, params} object."""


def normalize_plugin_binding(raw: Any, *, field: str) -> dict[str, Any]:
    """Return ``{type, ref?, params?}`` or ``{}`` when the slot is omitted.

    ``"cot"`` and ``{type: cot}`` are equivalent. An empty string is omission.
    """
    if raw is None:
        return {}
    if isinstance(raw, str):
        name = raw.strip()
        return {"type": name} if name else {}
    if isinstance(raw, dict):
        return dict(raw)
    raise PluginBindingError(
        f"{field} must be a plugin name or {{type, ref, params}} object, "
        f"got {type(raw).__name__}"
    )


def normalize_plugin_binding_lenient(raw: Any, *, field: str) -> dict[str, Any]:
    """``normalize_plugin_binding``, but a malformed slot is omission, not an error.

    For runtime call sites only (see module docstring). ``ctl`` already
    rejects this shape at ``compile``/``validate`` time via the strict form;
    by the time the kernel reads it, the field is either well-formed or the
    manifest never went through ``ctl`` — either way, defaulting is the same
    resilient behavior an omitted field already gets.
    """
    try:
        return normalize_plugin_binding(raw, field=field)
    except PluginBindingError:
        return {}


def plugin_binding_id(raw: Any, *, field: str) -> str:
    """Plugin name from a singleton slot (string or type/ref object)."""
    binding = normalize_plugin_binding(raw, field=field)
    return str(binding.get("type") or binding.get("ref") or "").strip()


def plugin_binding_params(raw: Any, *, field: str) -> dict[str, Any]:
    """Constructor/config kwargs (``params`` wins over legacy ``config``)."""
    binding = normalize_plugin_binding(raw, field=field)
    config = binding.get("config")
    params = dict(binding.get("params") or {})
    if isinstance(config, dict):
        params = {**config, **params}
    return params
