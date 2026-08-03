#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agent overlay merge — ported from mas-lab runtime/manifest/composition.py (RFC 7396 + agent rules)."""

from __future__ import annotations

from functools import lru_cache
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


_OVERLAY_PATCH_SCHEMA_FILES: dict[str, str] = {
    "Agent": "docs/schemas/runtime/fragments/overlay-agent-patch.schema.yaml",
    "MAS": "docs/schemas/runtime/fragments/overlay-mas-patch.schema.yaml",
    "Flavour": "docs/schemas/runtime/fragments/overlay-flavour-patch.schema.yaml",
    "Infra": "docs/schemas/runtime/fragments/overlay-infra-patch.schema.yaml",
}


def _repo_root() -> Path:
    # .../mas-lab/ctl/src/mas/ctl/overlay/merge.py -> parents[5] == repo root
    return Path(__file__).resolve().parents[5]


@lru_cache(maxsize=8)
def _load_yaml_schema(rel_path: str) -> dict[str, Any]:
    schema_path = _repo_root() / rel_path
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _format_semantic(meta: dict[str, Any]) -> str:
    strategy = str(meta.get("strategy") or "")
    extras: list[str] = []
    identity = meta.get("identity")
    if identity:
        extras.append(f"identity={identity}")
    if extras:
        return f"{strategy}({','.join(extras)})"
    return strategy


def _collect_merge_meta(
    schema: dict[str, Any],
    *,
    prefix: str = "",
 ) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    props = schema.get("properties")
    if not isinstance(props, dict):
        return out
    for key, raw_prop in props.items():
        if not isinstance(raw_prop, dict):
            continue
        path = f"{prefix}{key}"
        merge_meta = raw_prop.get("x-merge")
        if isinstance(merge_meta, dict):
            out[path] = dict(merge_meta)
        out.update(_collect_merge_meta(raw_prop, prefix=f"{path}."))
    return out

def _schema_property_keys(kind: str) -> frozenset[str]:
    rel_path = _OVERLAY_PATCH_SCHEMA_FILES.get(kind)
    if rel_path is None:
        return frozenset()
    schema = _load_yaml_schema(rel_path)
    props = schema.get("properties")
    if not isinstance(props, dict):
        return frozenset()
    return frozenset(str(k) for k in props.keys())


@lru_cache(maxsize=3)
def _overlay_merge_meta(kind: str) -> dict[str, dict[str, Any]]:
    rel_path = _OVERLAY_PATCH_SCHEMA_FILES.get(kind)
    if rel_path is None:
        return {}
    return _collect_merge_meta(_load_yaml_schema(rel_path))


def overlay_runtime_semantics() -> dict[str, dict[str, str]]:
    """Return non-trivial overlay merge semantics derived from schema x-merge metadata."""
    out: dict[str, dict[str, str]] = {}
    for kind in ("Agent", "MAS", "Flavour", "Infra"):
        out[kind] = {
            field: _format_semantic(meta)
            for field, meta in _overlay_merge_meta(kind).items()
        }
    return out


def _schema_kind_from_target(target_kind: str) -> str | None:
    normalized = str(target_kind or "").strip().lower()
    if normalized in ("agent",):
        return "Agent"
    if normalized in ("mas", "app", "workflow"):
        return "MAS"
    if normalized in ("flavour",):
        return "Flavour"
    if normalized in ("infra",):
        return "Infra"
    return None


def _validate_patch_fields_against_target_schema(overlay: dict[str, Any]) -> None:
    spec = overlay.get("spec") or {}
    patch = spec.get("patch")
    if not isinstance(patch, dict):
        return
    schema_kind = _schema_kind_from_target(str((spec.get("target") or {}).get("kind") or ""))
    if schema_kind is None:
        return
    allowed_fields = _schema_property_keys(schema_kind)
    for field in patch.keys():
        if str(field).startswith("x-"):
            continue
        if str(field) not in allowed_fields:
            raise OverlayTargetError(f"Unsupported {schema_kind} overlay patch field: {field}")


def _ops_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("$op"), dict):
        value = value["$op"]
    if not isinstance(value, dict):
        return None
    op_keys = {"replace", "add", "remove", "clear", "merge"}
    if not (set(value) & op_keys):
        return None
    return value


def _merge_list_ops(
    existing: list[Any],
    incoming: Any,
    *,
    dedupe_key=None,
) -> list[Any]:
    ops = _ops_dict(incoming)
    if ops is None:
        # Implicit replace ergonomics: raw list means "replace".
        if isinstance(incoming, list):
            return list(incoming)
        raise OverlayTargetError(
            "collection patch must be a raw list (implicit replace) or use '$op' "
            "(replace/add/remove/clear)"
        )

    if ops.get("clear") is True:
        result: list[Any] = []
    else:
        result = list(existing)

    if "replace" in ops:
        result = list(ops.get("replace") or [])

    if "remove" in ops:
        to_remove = list(ops.get("remove") or [])
        if dedupe_key is None:
            result = [item for item in result if item not in to_remove]
        else:
            remove_keys = {dedupe_key(item) for item in to_remove}
            result = [item for item in result if dedupe_key(item) not in remove_keys]

    if "add" in ops:
        for item in list(ops.get("add") or []):
            if dedupe_key is None:
                if item not in result:
                    result.append(item)
            else:
                keys = {dedupe_key(v) for v in result}
                key = dedupe_key(item)
                if key not in keys:
                    result.append(item)
        
    return result


def _merge_mapping_ops(existing: dict[str, Any], incoming: Any) -> dict[str, Any]:
    ops = _ops_dict(incoming)
    if ops is None:
        if isinstance(incoming, dict):
            # Implicit replace ergonomics for mapping fields.
            return deepcopy(incoming)
        raise OverlayTargetError(
            "mapping patch must be a raw object (implicit replace) or use '$op' "
            "(replace/merge/clear)"
        )
    if ops.get("clear") is True:
        result: dict[str, Any] = {}
    else:
        result = deepcopy(existing)
    if "replace" in ops:
        replace_val = ops.get("replace") or {}
        if not isinstance(replace_val, dict):
            raise OverlayTargetError("replace operation expects an object")
        result = deepcopy(replace_val)
    if "merge" in ops:
        merge_val = ops.get("merge") or {}
        if not isinstance(merge_val, dict):
            raise OverlayTargetError("merge operation expects an object")
        result = apply_merge_patch(result, deepcopy(merge_val))
    return result


def _plugin_entry_key(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and len(item) == 1:
        return str(next(iter(item.keys())))
    return str(item)


def _merge_plugin_list_ops(existing: list[Any], incoming: Any) -> list[Any]:
    ops = _ops_dict(incoming)
    if ops is None:
        if isinstance(incoming, list):
            return list(incoming)
        raise OverlayTargetError(
            "plugin-list patch must be a raw list (implicit replace) or use '$op' "
            "(replace/add/remove/clear)"
        )

    if ops.get("clear") is True:
        result: list[Any] = []
    else:
        result = list(existing)

    if "replace" in ops:
        result = list(ops.get("replace") or [])

    if "remove" in ops:
        remove_keys = {str(v) for v in list(ops.get("remove") or [])}
        result = [item for item in result if _plugin_entry_key(item) not in remove_keys]

    if "add" in ops:
        keys = {_plugin_entry_key(item) for item in result}
        for item in list(ops.get("add") or []):
            key = _plugin_entry_key(item)
            if key not in keys:
                result.append(item)
                keys.add(key)

    return result


def _merge_value_by_meta(existing: Any, incoming: Any, meta: dict[str, Any]) -> Any:
    strategy = str(meta.get("strategy") or "")

    if incoming is None:
        return None

    if strategy == "list_ops":
        dedupe_key = None
        identity = str(meta.get("identity") or "")
        if identity == "tool_remove_key":
            dedupe_key = _tool_remove_key
        existing_list = list(existing or []) if isinstance(existing, list) else []
        return _merge_list_ops(existing_list, incoming, dedupe_key=dedupe_key)

    if strategy == "plugin_list_ops":
        existing_list = list(existing or []) if isinstance(existing, list) else []
        return _merge_plugin_list_ops(existing_list, incoming)

    if strategy == "mapping_ops":
        existing_map = existing if isinstance(existing, dict) else {}
        return _merge_mapping_ops(existing_map, incoming)

    if strategy == "mapping_merge_or_ops":
        existing_map = existing if isinstance(existing, dict) else {}
        if isinstance(incoming, dict) and _ops_dict(incoming) is not None:
            return _merge_mapping_ops(existing_map, incoming)
        if isinstance(incoming, dict) and isinstance(existing_map, dict):
            merged = deepcopy(existing_map)
            merged.update(incoming)
            return merged
        return deepcopy(incoming)

    if strategy == "context_merge":
        if isinstance(incoming, dict) and isinstance(existing, dict):
            merged = deepcopy(existing)
            merged.update(incoming)
            return merged
        if isinstance(incoming, dict):
            return deepcopy(incoming)
        if isinstance(incoming, list):
            existing_list = list(existing or []) if isinstance(existing, list) else []
            existing_list.extend(incoming)
            return existing_list
        return deepcopy(incoming)

    if strategy == "execution_merge":
        base_block = existing if isinstance(existing, dict) else {}
        ov_block = incoming or {}
        if isinstance(ov_block, dict):
            merged = deepcopy(base_block)
            for k, v in ov_block.items():
                if v is None:
                    merged.pop(k, None)
                elif k == "policies" and isinstance(v, list):
                    merged["policies"] = list(v)
                elif isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
        return deepcopy(ov_block)

    if strategy == "replace":
        return deepcopy(incoming)

    return deepcopy(incoming)


def _agency_entry_key(entry: dict[str, Any]) -> str | None:
    key = entry.get("id") or entry.get("name")
    if key is None:
        return None
    text = str(key).strip()
    return text or None


def apply_merge_patch(target: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return patch
    if not isinstance(target, dict):
        target = {}
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            target[key] = apply_merge_patch(target.get(key, {}), value)
        else:
            target[key] = value
    return target


def _tool_remove_key(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("ref") or item)
    return str(item)


class OverlayTargetError(ValueError):
    """A Flavour-targeted overlay patch contains a key that isn't deployment posture."""


def merge_flavour_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge a ``target.kind: Flavour`` overlay patch into a Flavour manifest.

    Deliberately narrow: only the surviving Flavour deployment-posture keys
    (see ``_FLAVOUR_PATCH_KEYS``) may be patched. ``observability``/``control``
    use the same plugin-list merge as agent overlays (:func:`_merge_plugin_list_field`)
    since the field shape — not the manifest kind — determines the semantics.
    """
    merged = deepcopy(base)
    if "spec" not in overlay:
        return merged

    overlay_spec = overlay["spec"]
    if "patch" in overlay_spec and isinstance(overlay_spec["patch"], dict):
        overlay_spec = overlay_spec["patch"]

    allowed_flavour_keys = _schema_property_keys("Flavour")
    unknown = set(overlay_spec) - allowed_flavour_keys
    if unknown:
        raise OverlayTargetError(
            f"overlay patch for target.kind: Flavour contains non-deployment-posture "
            f"key(s) {sorted(unknown)!r} — see docs/design/flavour-boundary.md"
        )

    base_spec = merged.setdefault("spec", {})
    flavour_meta = _overlay_merge_meta("Flavour")

    for key, ov_val in overlay_spec.items():
        meta = flavour_meta.get(key)
        if meta is None:
            base_spec[key] = deepcopy(ov_val)
            continue
        base_spec[key] = _merge_value_by_meta(base_spec.get(key), ov_val, meta)

    return merged


def merge_agent_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    if "spec" not in overlay:
        return merged

    overlay_spec = overlay["spec"]
    if "patch" in overlay_spec and isinstance(overlay_spec["patch"], dict):
        overlay_spec = overlay_spec["patch"]
    base_spec = merged.setdefault("spec", {})
    agent_meta = _overlay_merge_meta("Agent")

    for key, incoming in overlay_spec.items():
        if key == "context_manager" and isinstance(incoming, dict):
            base_cm = base_spec.get("context_manager") or {}
            for cm_key, cm_val in incoming.items():
                meta = agent_meta.get(f"context_manager.{cm_key}")
                if meta is not None:
                    base_cm[cm_key] = _merge_value_by_meta(base_cm.get(cm_key), cm_val, meta)
                elif isinstance(base_cm.get(cm_key), list):
                    items = list(base_cm.get(cm_key) or [])
                    items.extend(list(cm_val or []) if isinstance(cm_val, list) else [cm_val])
                    base_cm[cm_key] = items
                else:
                    base_cm[cm_key] = cm_val
            base_spec["context_manager"] = base_cm
            continue

        meta = agent_meta.get(key)
        if meta is not None:
            base_spec[key] = _merge_value_by_meta(base_spec.get(key), incoming, meta)
            continue

        if isinstance(incoming, dict) and isinstance(base_spec.get(key), dict):
            merged_map = deepcopy(base_spec.get(key) or {})
            merged_map.update(incoming)
            base_spec[key] = merged_map
        else:
            base_spec[key] = deepcopy(incoming)

    return merged


def merge_mas_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge MAS/App/Workflow overlay patch into base manifest."""
    merged = deepcopy(base)
    overlay_spec = overlay.get("spec") or {}
    patch = overlay_spec.get("patch") if isinstance(overlay_spec.get("patch"), dict) else overlay_spec
    if not isinstance(patch, dict) or not patch:
        return merged

    base_spec = merged.setdefault("spec", {})
    mas_meta = _overlay_merge_meta("MAS")

    special_keys = {"governance", "agents", "agents_add", "agents_remove"}
    for key, value in patch.items():
        if key in special_keys:
            continue
        meta = mas_meta.get(key)
        if meta is not None:
            base_spec[key] = _merge_value_by_meta(base_spec.get(key), value, meta)
        else:
            if isinstance(value, dict) and isinstance(base_spec.get(key), dict):
                base_spec[key] = apply_merge_patch(deepcopy(base_spec[key]), value)
            else:
                base_spec[key] = deepcopy(value)

    overlay_agents = patch.get("agents")
    if isinstance(overlay_agents, dict) and _ops_dict(overlay_agents) is not None:
        ops = _ops_dict(overlay_agents) or {}
        agency = base_spec.setdefault("agency", {})
        existing_agents = list(agency.get("agents") or [])
        if ops.get("clear") is True:
            existing_agents = []
        if "replace" in ops:
            existing_agents = list(deepcopy(ops.get("replace") or []))
        if "remove" in ops:
            rm = {str(x) for x in list(ops.get("remove") or [])}
            existing_agents = [
                a for a in existing_agents if not (isinstance(a, dict) and _agency_entry_key(a) in rm)
            ]
        if "add" in ops:
            existing_keys = {
                _agency_entry_key(a)
                for a in existing_agents
                if isinstance(a, dict) and _agency_entry_key(a) is not None
            }
            for entry in list(ops.get("add") or []):
                if not isinstance(entry, dict):
                    continue
                key = _agency_entry_key(entry)
                if key is not None and key not in existing_keys:
                    existing_agents.append(deepcopy(entry))
                    existing_keys.add(key)
        agency["agents"] = existing_agents
        base_spec["agency"] = agency
    elif isinstance(overlay_agents, dict):
        agency = base_spec.setdefault("agency", {})
        agents_list = list(agency.get("agents") or [])
        by_id = {
            str(a.get("id") or a.get("name")): a
            for a in agents_list
            if isinstance(a, dict) and (a.get("id") or a.get("name"))
        }
        for agent_id, per_agent in overlay_agents.items():
            if not isinstance(per_agent, dict):
                continue
            target = by_id.get(str(agent_id))
            if target is None:
                continue
            if "ref" in per_agent:
                target["ref"] = deepcopy(per_agent["ref"])
            agent_spec = target.setdefault("spec", {})
            per_agent_overlay = {"spec": {"patch": deepcopy(per_agent)}}
            merged_agent = merge_agent_overlay({"spec": deepcopy(agent_spec)}, per_agent_overlay)
            agent_spec.clear()
            agent_spec.update(merged_agent.get("spec", {}))

    if patch.get("agents_remove"):
        rm_values = _merge_value_by_meta(
            [],
            patch["agents_remove"],
            mas_meta.get("agents_remove", {"strategy": "list_ops", "identity": "value"}),
        )
        rm = {str(x) for x in rm_values}
        agency = base_spec.get("agency") or {}
        agents_list = agency.get("agents") or []
        agency["agents"] = [
            a for a in agents_list if not (isinstance(a, dict) and _agency_entry_key(a) in rm)
        ]
        base_spec["agency"] = agency

    if patch.get("agents_add"):
        agency = base_spec.setdefault("agency", {})
        agents_add_ops = _ops_dict(patch["agents_add"]) if isinstance(patch["agents_add"], dict) else None
        if isinstance(agents_add_ops, dict) and agents_add_ops.get("clear") is True:
            agency["agents"] = []
        existing = {
            _agency_entry_key(a)
            for a in agency.get("agents") or []
            if isinstance(a, dict) and _agency_entry_key(a) is not None
        }
        entries = agents_add_ops.get("add") if isinstance(agents_add_ops, dict) else patch["agents_add"]
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            key = _agency_entry_key(entry)
            if key is not None and key not in existing:
                agency.setdefault("agents", []).append(deepcopy(entry))
                existing.add(key)

    return merged


def merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge an Agent, MAS, or Flavour patch overlay into a base manifest.

    Dispatch is strict by canonical ``spec.target.kind``: ``MAS`` ->
    :func:`merge_mas_overlay`, ``Flavour`` -> :func:`merge_flavour_overlay`,
    ``Agent`` -> :func:`merge_agent_overlay`.
    """
    from mas.ctl.overlay.normalize import normalize_overlay

    if "spec" not in overlay:
        base_kind = str(base.get("kind", "")).lower()
        if base_kind in ("mas", "app", "workflow"):
            return merge_mas_overlay(base, overlay)
        if base_kind == "flavour":
            return merge_flavour_overlay(base, overlay)
        return merge_agent_overlay(base, overlay)

    spec = overlay.get("spec") or {}
    canonical = (
        overlay.get("apiVersion") == "mas/v1"
        and overlay.get("kind") == "Overlay"
        and isinstance((spec.get("target") or {}).get("kind"), str)
        and isinstance(spec.get("patch"), dict)
        and isinstance(spec.get("target"), dict)
        and bool((spec.get("target") or {}).get("kind"))
    )
    if not canonical:
        overlay = normalize_overlay(overlay, name=str((overlay.get("metadata") or {}).get("name") or "overlay"))

    _validate_patch_fields_against_target_schema(overlay)

    target_kind = str((overlay.get("spec") or {}).get("target", {}).get("kind", "")).lower()
    if target_kind in ("mas", "app", "workflow"):
        return merge_mas_overlay(base, overlay)
    if target_kind == "flavour":
        return merge_flavour_overlay(base, overlay)
    if target_kind == "infra":
        merged = deepcopy(base)
        patch = deepcopy((overlay.get("spec") or {}).get("patch") or {})
        if isinstance(patch, dict):
            merged_spec = apply_merge_patch(deepcopy(merged.get("spec") or {}), patch)
            merged["spec"] = merged_spec
            return merged
        return merged
    if target_kind == "agent":
        return merge_agent_overlay(base, overlay)
    raise OverlayTargetError(
        "overlay spec.target.kind must be one of Agent, MAS, Flavour, Infra"
    )
