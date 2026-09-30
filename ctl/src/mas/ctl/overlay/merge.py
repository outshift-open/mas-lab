#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agent overlay merge — ported from mas-lab runtime/manifest/composition.py (RFC 7396 + agent rules)."""

from __future__ import annotations

import logging
from copy import deepcopy
from functools import lru_cache
from typing import Any

import yaml
from mas.ctl.validate.schemas import schema_root
from mas.runtime.spec.plugin_binding import normalize_plugin_binding, plugin_binding_id

logger = logging.getLogger(__name__)


# Every kind reads merge metadata straight off its own canonical schema --
# every overlay-patchable field carries its own x-merge annotation inline on
# the field it actually describes, so adding a new patchable field is a
# single edit in a single file (docs/schemas/runtime/<kind>.schema.yaml),
# not a second hand-maintained overlay-*-patch fragment kept in sync by hand.
_OVERLAY_PATCH_SCHEMA_FILES: dict[str, str] = {
    "Agent": "runtime/agent.schema.yaml",
    "MAS": "runtime/mas.schema.yaml",
    "Flavour": "runtime/flavour.schema.yaml",
    "Infra": "runtime/infra.schema.yaml",
}

# Where to start reading "properties" from, per schema file, relative to that
# file's own root -- every canonical kind schema nests its patchable fields
# one level deeper (properties.spec.properties.*) than the root.
_OVERLAY_PATCH_SCHEMA_ROOT: dict[str, tuple[str, ...]] = {
    "Agent": ("properties", "spec"),
    "MAS": ("properties", "spec"),
    "Flavour": ("properties", "spec"),
    "Infra": ("properties", "spec"),
}


@lru_cache(maxsize=8)
def _load_yaml_schema(rel_path: str) -> dict[str, Any]:
    schema_path = schema_root() / rel_path
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _overlay_patch_root_schema(kind: str) -> dict[str, Any]:
    """The schema node whose ``properties`` are this kind's patchable fields."""
    rel_path = _OVERLAY_PATCH_SCHEMA_FILES.get(kind)
    if rel_path is None:
        return {}
    schema = _load_yaml_schema(rel_path)
    for key in _OVERLAY_PATCH_SCHEMA_ROOT.get(kind, ()):
        schema = schema.get(key) or {}
    return schema


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
    schema = _overlay_patch_root_schema(kind)
    props = schema.get("properties")
    if not isinstance(props, dict):
        return frozenset()
    return frozenset(str(k) for k in props.keys())


@lru_cache(maxsize=3)
def _overlay_merge_meta(kind: str) -> dict[str, dict[str, Any]]:
    return _collect_merge_meta(_overlay_patch_root_schema(kind))


def overlay_runtime_semantics() -> dict[str, dict[str, str]]:
    """Return non-trivial overlay merge semantics derived from schema x-merge metadata."""
    out: dict[str, dict[str, str]] = {}
    for kind in ("Agent", "MAS", "Flavour", "Infra"):
        out[kind] = {field: _format_semantic(meta) for field, meta in _overlay_merge_meta(kind).items()}
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
            "collection patch must be a raw list (implicit replace) or use '$op' (replace/add/remove/clear)"
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


def _as_fragment_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def merge_context_chunk(existing: Any, incoming: Any) -> Any:
    """Merge one spec.context.<key> overlay patch value onto its base value.

    A plain value (string/{ref}/list) fully replaces the base chunk -- implicit
    replace ergonomics, consistent with every other overlay merge strategy in
    this repo. A `{"$op": {replace|add|remove|clear}}` value instead operates on
    the base chunk's fragment list via the same list-patch semantics spec.tools
    already uses (_merge_list_ops above), coercing a scalar base value to a
    one-item list first -- so an overlay can add or remove a single fragment
    (e.g. append one sentence to spec.context.role) without restating the rest.
    """
    if _ops_dict(incoming) is None:
        return deepcopy(incoming)
    return _merge_list_ops(_as_fragment_list(existing), incoming)


def merge_context_map(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge an overlay's spec.context patch onto the base spec.context map."""
    merged = deepcopy(existing) if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if value is None:
            merged.pop(key, None)
            continue
        merged[key] = merge_context_chunk(merged.get(key), value)
    return merged


def _merge_mapping_ops(existing: dict[str, Any], incoming: Any) -> dict[str, Any]:
    ops = _ops_dict(incoming)
    if ops is None:
        if isinstance(incoming, dict):
            # Implicit replace ergonomics for mapping fields.
            return deepcopy(incoming)
        raise OverlayTargetError(
            "mapping patch must be a raw object (implicit replace) or use '$op' (replace/merge/clear)"
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
            "plugin-list patch must be a raw list (implicit replace) or use '$op' (replace/add/remove/clear)"
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
        existing_list = list(existing or []) if isinstance(existing, list) else []
        try:
            return _merge_list_ops(existing_list, incoming, dedupe_key=None)
        except ValueError as exc:
            raise OverlayTargetError(str(exc)) from exc

    if strategy == "named_list_union":
        identity = str(meta.get("identity") or "name")
        existing_list = list(existing or []) if isinstance(existing, list) else []

        def _item_key(item: Any) -> str:
            if isinstance(item, dict):
                if identity == "id":
                    return str(item.get("id") or item.get("model") or "main")
                return str(item.get(identity) or "")
            return str(item)

        if _ops_dict(incoming) is not None:
            try:
                return _merge_list_ops(existing_list, incoming, dedupe_key=_item_key)
            except ValueError as exc:
                raise OverlayTargetError(str(exc)) from exc
        if not isinstance(incoming, list):
            raise OverlayTargetError(
                "named_list_union patch must be a raw list or use '$op' (replace/add/remove/clear)"
            )
        result = [deepcopy(item) for item in existing_list]
        index_by_key = {_item_key(item): i for i, item in enumerate(result) if _item_key(item)}
        for item in incoming:
            copied = deepcopy(item)
            key = _item_key(copied)
            if key and key in index_by_key:
                result[index_by_key[key]] = copied
            else:
                result.append(copied)
                if key:
                    index_by_key[key] = len(result) - 1
        return result

    if strategy == "named_list_merge":
        identity = str(meta.get("identity") or "id")
        existing_list = list(existing or []) if isinstance(existing, list) else []

        def _merge_key(item: Any) -> str:
            if isinstance(item, dict):
                if identity == "id":
                    return str(item.get("id") or item.get("model") or "main")
                return str(item.get(identity) or item.get("id") or item.get("model") or "")
            return str(item)

        def _has_explicit_identity(item: Any) -> bool:
            if not isinstance(item, dict):
                return False
            key = "id" if identity == "id" else identity
            return bool(item.get(key))

        if _ops_dict(incoming) is not None:
            try:
                return _merge_list_ops(existing_list, incoming, dedupe_key=_merge_key)
            except ValueError as exc:
                raise OverlayTargetError(str(exc)) from exc
        if not isinstance(incoming, list):
            raise OverlayTargetError(
                "named_list_merge patch must be a raw list or use '$op' (replace/add/remove/clear)"
            )
        result = [deepcopy(item) for item in existing_list]
        index_by_key = {_merge_key(item): i for i, item in enumerate(result) if _merge_key(item)}
        for pos, item in enumerate(incoming):
            copied = deepcopy(item)
            key = _merge_key(copied)
            target_index = index_by_key.get(key) if key else None
            if (
                target_index is None
                and not _has_explicit_identity(copied)
                and pos < len(result)
                and len(existing_list) == 1
            ):
                # No explicit identity on the patch item and exactly one base
                # row — fall back to matching that row instead of appending a
                # duplicate (the derived key, e.g. from "model", may not match
                # the base row's own identity, such as a custom "id"). With 2+
                # base rows position carries no meaning, so an unmatched key
                # is treated as a genuine new addition instead of a guess.
                target_index = pos
            if target_index is not None:
                current = result[target_index]
                if isinstance(current, dict) and isinstance(copied, dict):
                    result[target_index] = apply_merge_patch(deepcopy(current), copied)
                else:
                    result[target_index] = copied
                if key:
                    index_by_key[key] = target_index
            else:
                result.append(copied)
                if key:
                    index_by_key[key] = len(result) - 1
        return result

    if strategy == "plugin_list_ops":
        existing_list = list(existing or []) if isinstance(existing, list) else []
        return _merge_plugin_list_ops(existing_list, incoming)

    if strategy == "mapping_ops":
        existing_map = existing if isinstance(existing, dict) else {}
        return _merge_mapping_ops(existing_map, incoming)

    if strategy == "plugin_binding_merge":
        return _merge_plugin_binding(existing, incoming)

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
        if isinstance(incoming, dict):
            return merge_context_map(existing, incoming)
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


def _plugin_binding_object(raw: Any) -> dict[str, Any]:
    return deepcopy(normalize_plugin_binding(raw, field="plugin binding"))


def _deep_merge_maps(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Recurse dict values so a partial nested patch keeps sibling keys."""
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge_maps(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _merge_plugin_binding(existing: Any, incoming: Any) -> Any:
    """Merge a singleton plugin slot (string shorthand or {type, ref, params}).

    A type/ref change replaces the binding (no leftover constructor kwargs).
    Same type, or params-only overlay, deep-merges nested ``params``/``config``.
    """
    if isinstance(incoming, str) and incoming.strip():
        return normalize_plugin_binding(incoming, field="plugin binding")
    base = _plugin_binding_object(existing)
    if not isinstance(incoming, dict):
        return deepcopy(incoming)
    if _ops_dict(incoming) is not None:
        return _merge_mapping_ops(base, incoming)
    incoming_id = plugin_binding_id(incoming, field="plugin binding")
    base_id = plugin_binding_id(base, field="plugin binding")
    if incoming_id and base_id and incoming_id != base_id:
        return deepcopy(incoming)
    merged = deepcopy(base)
    for key, value in incoming.items():
        if (
            key in {"params", "config"}
            and isinstance(merged.get(key), dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge_maps(merged[key], value)
        elif isinstance(merged.get(key), list) and isinstance(value, list):
            merged[key] = list(merged[key]) + list(value)
        else:
            merged[key] = deepcopy(value)
    return merged


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


def _is_extension_key(key: Any) -> bool:
    return str(key).startswith("x-")


def _extension_fields(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return {}
    return {k: deepcopy(v) for k, v in doc.items() if _is_extension_key(k)}


def apply_document_extensions(target: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Copy overlay document-level ``x-*`` fields onto the composed target root.

    Extension keys live on the overlay document root (and may also appear under
    ``spec.patch``). Runtime merge of spec fields ignores these keys; they must
    land on the target document root so they match MAS/Agent schemas, not
    ``spec``. Later overlays win; nested dicts are RFC 7396-merged. A null
    value deletes the key.
    """
    patch = (overlay.get("spec") or {}).get("patch") if isinstance(overlay.get("spec"), dict) else None
    for src in (_extension_fields(overlay), _extension_fields(patch)):
        for key, value in src.items():
            existing = target.get(key)
            if value is None:
                target.pop(key, None)
            elif isinstance(existing, dict) and isinstance(value, dict):
                target[key] = apply_merge_patch(deepcopy(existing), deepcopy(value))
            else:
                target[key] = deepcopy(value)
    return target


class OverlayTargetError(ValueError):
    """Overlay target kind, name, or patch field does not match the base document."""


_ENTRY_AGENT_KEY = "$entry"


def _workflow_entry(spec: dict[str, Any]) -> str:
    wf = spec.get("workflow")
    if not isinstance(wf, dict):
        return ""
    entry = wf.get("entry")
    return str(entry).strip() if entry is not None else ""


def _resolve_mas_agent_patches(overlay_agents: dict[str, Any], *, entry: str) -> dict[str, Any]:
    """Map ``patch.agents.$entry`` onto ``spec.workflow.entry`` after the workflow patch."""
    if _ENTRY_AGENT_KEY not in overlay_agents:
        return overlay_agents
    if not entry:
        raise OverlayTargetError("patch.agents.$entry requires spec.workflow.entry on the merged MAS")
    if entry in overlay_agents:
        raise OverlayTargetError(
            f"patch.agents.$entry and patch.agents[{entry!r}] both set; "
            "use $entry alone — it already names the workflow entry agent"
        )
    resolved: dict[str, Any] = {}
    for agent_id, per_agent in overlay_agents.items():
        key = entry if agent_id == _ENTRY_AGENT_KEY else agent_id
        resolved[key] = per_agent
    return resolved


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
    unknown = {k for k in overlay_spec if not _is_extension_key(k)} - allowed_flavour_keys
    if unknown:
        raise OverlayTargetError(
            f"overlay patch for target.kind: Flavour contains non-deployment-posture "
            f"key(s) {sorted(unknown)!r} — see docs/design/flavour-boundary.md"
        )

    base_spec = merged.setdefault("spec", {})
    flavour_meta = _overlay_merge_meta("Flavour")

    for key, ov_val in overlay_spec.items():
        if _is_extension_key(key):
            continue
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
        if _is_extension_key(key):
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

    special_keys = {"agents", "agents_add", "agents_remove"}
    for key, value in patch.items():
        if key in special_keys or _is_extension_key(key):
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
            existing_agents = [a for a in existing_agents if not (isinstance(a, dict) and _agency_entry_key(a) in rm)]
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
        had_entry_key = _ENTRY_AGENT_KEY in overlay_agents
        entry_id = _workflow_entry(base_spec)
        overlay_agents = _resolve_mas_agent_patches(overlay_agents, entry=entry_id)
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
                if had_entry_key and str(agent_id) == entry_id:
                    raise OverlayTargetError(
                        f"patch.agents.$entry resolved to {agent_id!r}, which is not in spec.agency.agents"
                    )
                continue
            # Ref-based entries have no real content here yet (it lives in the
            # ref'd file, loaded later by apply_agency_entry_overlay) -- hand
            # context through raw rather than pre-merging $op.add against an
            # empty spec, or the base gets silently dropped. Check "ref", not
            # spec emptiness: spec fills in here after the first overlay.
            is_ref_based = "ref" in target and str(target.get("kind") or "").lower() != "agent"
            if "ref" in per_agent:
                target["ref"] = deepcopy(per_agent["ref"])
            legacy_transport_keys = {"agent_comm", "agent_transport", "expose"} & per_agent.keys()
            if legacy_transport_keys:
                raise OverlayTargetError(
                    "MAS agency overlays cannot set transport or exposure fields "
                    f"{sorted(legacy_transport_keys)!r}; use an infra Application endpoint "
                    "for remote peers and `mas-ctl serve` for inbound exposure"
                )
            agent_spec = target.setdefault("spec", {})
            raw_context = per_agent.get("context") if is_ref_based else None
            per_agent_for_merge = (
                {k: v for k, v in per_agent.items() if k not in {"context", "ref"}}
                if raw_context is not None
                else {k: v for k, v in per_agent.items() if k != "ref"}
            )
            per_agent_overlay = {"spec": {"patch": deepcopy(per_agent_for_merge)}}
            merged_agent = merge_agent_overlay({"spec": deepcopy(agent_spec)}, per_agent_overlay)
            agent_spec.clear()
            agent_spec.update(merged_agent.get("spec", {}))
            if raw_context is not None:
                agent_spec["context"] = deepcopy(raw_context)

    if patch.get("agents_remove"):
        rm_values = _merge_value_by_meta(
            [],
            patch["agents_remove"],
            mas_meta.get("agents_remove", {"strategy": "list_ops", "identity": "value"}),
        )
        rm = {str(x) for x in rm_values}
        agency = base_spec.get("agency") or {}
        agents_list = agency.get("agents") or []
        agency["agents"] = [a for a in agents_list if not (isinstance(a, dict) and _agency_entry_key(a) in rm)]
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


def _nested_agent_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Agency rows that an Agent overlay can fan out onto.

    ``spec.agency.agents`` wins when present (even if empty); otherwise
    ``spec.agents``. Empty agency.agents does not fall through to spec.agents —
    that list is the declared participant set.
    """
    agency = spec.get("agency")
    if isinstance(agency, dict) and "agents" in agency:
        agents = agency.get("agents") or []
        return [e for e in agents if isinstance(e, dict)]
    agents = spec.get("agents")
    if isinstance(agents, list):
        return [e for e in agents if isinstance(e, dict)]
    return []


def _base_is_mas(base: dict[str, Any]) -> bool:
    kind = str(base.get("kind") or "").lower()
    if kind in ("mas", "app", "workflow"):
        return True
    spec = base.get("spec") or {}
    return bool(_nested_agent_rows(spec if isinstance(spec, dict) else {}))


def _overlay_target_name(overlay: dict[str, Any]) -> str | None:
    name = ((overlay.get("spec") or {}).get("target") or {}).get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _row_matches_agent_target(row: dict[str, Any], target_name: str) -> bool:
    keys = {
        str(row.get("id") or "").strip(),
        str(row.get("name") or "").strip(),
        str((row.get("metadata") or {}).get("name") or "").strip(),
    }
    keys.discard("")
    return target_name in keys


def _is_inline_agent_row(row: dict[str, Any]) -> bool:
    return str(row.get("kind") or "").lower() == "agent" and isinstance(row.get("spec"), dict)


def fanout_agent_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Copy a ``target.kind: Agent`` overlay onto nested MAS agency rows.

    ``compile`` already merges Agent overlays onto separately loaded agent
    YAML. ``compose`` / ``run-mas`` only call :func:`merge_overlay` on the MAS
    document, so without this step the patch never reaches
    ``spec.agency.agents`` and instantiate loads the unpatched files.

    ``spec.target.name``, when set, selects one row (id, name, or
    metadata.name). Use the agency row id, which should match the agent
    YAML ``metadata.name`` when the overlay is reused on both. Omit the
    name to patch every nested agent. Zero matches is an error — an Agent
    overlay that attaches nowhere would look applied.
    """
    merged = deepcopy(base)
    spec = merged.setdefault("spec", {})
    if not isinstance(spec, dict):
        spec = {}
        merged["spec"] = spec
    rows = _nested_agent_rows(spec)
    target_name = _overlay_target_name(overlay)
    matched = 0
    for row in rows:
        if target_name and not _row_matches_agent_target(row, target_name):
            continue
        if _is_inline_agent_row(row):
            updated = merge_agent_overlay(row, overlay)
            row.clear()
            row.update(updated)
        else:
            stub = {
                "apiVersion": "mas/v1",
                "kind": "Agent",
                "spec": deepcopy(row.get("spec") or {}),
            }
            updated = merge_agent_overlay(stub, overlay)
            row["spec"] = deepcopy(updated.get("spec") or {})
        matched += 1
    if matched == 0:
        named = f" named {target_name!r}" if target_name else ""
        raise OverlayTargetError(
            f"target.kind: Agent overlay{named} matched no agents in "
            "spec.agency.agents / spec.agents"
        )
    return merged


def merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge an Agent, MAS, Flavour, or Infra patch overlay into a base manifest.

    Dispatch is strict by canonical ``spec.target.kind``: ``MAS`` ->
    :func:`merge_mas_overlay`, ``Flavour`` -> :func:`merge_flavour_overlay`,
    ``Agent`` on an Agent document -> :func:`merge_agent_overlay`, ``Agent``
    on a MAS -> :func:`fanout_agent_overlay`.
    """
    from mas.ctl.overlay.normalize import normalize_overlay

    if "spec" not in overlay:
        base_kind = str(base.get("kind", "")).lower()
        if base_kind in ("mas", "app", "workflow"):
            merged = merge_mas_overlay(base, overlay)
        elif base_kind == "flavour":
            merged = merge_flavour_overlay(base, overlay)
        else:
            merged = merge_agent_overlay(base, overlay)
        return apply_document_extensions(merged, overlay)

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
        merged = merge_mas_overlay(base, overlay)
    elif target_kind == "flavour":
        merged = merge_flavour_overlay(base, overlay)
    elif target_kind == "infra":
        merged = deepcopy(base)
        patch = deepcopy((overlay.get("spec") or {}).get("patch") or {})
        if isinstance(patch, dict):
            patch = {k: v for k, v in patch.items() if not _is_extension_key(k)}
            merged_spec = apply_merge_patch(deepcopy(merged.get("spec") or {}), patch)
            merged["spec"] = merged_spec
    elif target_kind == "agent":
        if _base_is_mas(base):
            merged = fanout_agent_overlay(base, overlay)
        else:
            merged = merge_agent_overlay(base, overlay)
    else:
        raise OverlayTargetError("overlay spec.target.kind must be one of Agent, MAS, Flavour, Infra")
    return apply_document_extensions(merged, overlay)
