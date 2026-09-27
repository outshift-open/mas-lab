#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Spot JSON Schema ``deprecated: true`` properties and removed experiment keys.

Draft-07 ignores ``deprecated``, so validators must walk the schema themselves.
Removed keys are rejected by ``additionalProperties: false``; this module
supplies replacement hints for those error messages.
"""

from __future__ import annotations

from typing import Any

# Keys that used to appear on experiment: and are now schema-rejected.
REMOVED_EXPERIMENT_KEYS = {
    "pipeline_bind": "declare hooks under run/item/scenario/post",
    "pipeline": "use run/item/scenario/post hooks (CLI --depth exp|scenario|item|run)",
    "output_dir": "remove; output paths are derived from lab layout",
    "flavours": "use default_flavour (library-standard flavours)",
    "plots": "declare plot steps in experiment-level post: or scenario.post",
    "mas": "use application: {app|manifest, configs_dir}",
}

_LEVEL_SECTION_KEYS = frozenset({"pre", "post", "artifacts", "n_runs"})
_MAS_BINDING_KEYS = frozenset({"app", "manifest", "configs_dir", "base_scenario"})


def _deref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    merged = dict(schema)
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref.rsplit("/", 1)[-1]
        target = (root.get("$defs") or {}).get(name) or {}
        merged = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
    if "allOf" in merged:
        acc: dict[str, Any] = {}
        for part in merged.get("allOf") or []:
            if isinstance(part, dict):
                acc.update(_deref(part, root))
        extra = {k: v for k, v in merged.items() if k != "allOf"}
        acc.update(extra)
        merged = acc
    return merged


def collect_deprecated_uses(
    instance: Any,
    schema: dict[str, Any] | None,
    *,
    root: dict[str, Any] | None = None,
    path: str = "",
) -> list[str]:
    """Return warning strings for instance keys marked ``deprecated: true``."""
    if not isinstance(schema, dict):
        return []
    root = root if root is not None else schema
    schema = _deref(schema, root)
    msgs: list[str] = []
    if schema.get("deprecated") and path:
        replaced = schema.get("x-replaced-by")
        hint = f"; use {replaced}" if replaced else ""
        msgs.append(f"{path} is deprecated{hint}")
    if isinstance(instance, dict):
        props = schema.get("properties") or {}
        for key, sub in props.items():
            if key not in instance:
                continue
            child_path = f"{path}.{key}" if path else str(key)
            msgs.extend(
                collect_deprecated_uses(
                    instance[key], sub, root=root, path=child_path
                )
            )
    elif isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(instance):
                child_path = f"{path}[{i}]" if path else f"[{i}]"
                msgs.extend(
                    collect_deprecated_uses(item, items, root=root, path=child_path)
                )
    return msgs


def collect_experiment_deprecations(
    data: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    """Deprecated experiment.yaml keys plus application-as-pipeline-level."""
    msgs = collect_deprecated_uses(data, schema, root=schema)
    exp = data.get("experiment")
    if not isinstance(exp, dict):
        return msgs
    app = exp.get("application")
    if isinstance(app, dict):
        keys = set(app)
        if keys & _LEVEL_SECTION_KEYS and not keys & _MAS_BINDING_KEYS:
            msgs.append(
                "experiment.application is used as a pipeline level; "
                "use experiment-level post: (CLI --depth exp)"
            )
    return msgs


def hint_for_removed_experiment_key(field: str) -> str:
    hint = REMOVED_EXPERIMENT_KEYS.get(field, "")
    if hint:
        return f"{field} was removed; {hint}"
    return ""
