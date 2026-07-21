#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agent overlay merge — ported from mas-lab runtime/manifest/composition.py (RFC 7396 + agent rules)."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


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


def _merge_plugin_list_field(base_spec: dict[str, Any], overlay_spec: dict[str, Any], key: str) -> None:
    """Merge a plugin-list field (``observability``, ``control``) in place on *base_spec*.

    Shared by :func:`merge_agent_overlay` and :func:`merge_flavour_overlay` — the
    merge semantics don't depend on whether the base spec belongs to an Agent
    or a Flavour manifest, only on the field's shape (a list of plugin ids /
    ``{plugin_id: config}`` entries, per ``fragments/observability-binding.
    schema.yaml`` and ``fragments/control-binding.schema.yaml``).
    """
    ov_val = overlay_spec[key]
    if isinstance(ov_val, list):
        # List replaces base (mas-lab parity).
        base_spec[key] = list(ov_val)
    elif isinstance(ov_val, dict):
        base_val = base_spec.get(key) or {}
        if isinstance(base_val, list):
            base_spec[key] = ov_val
        else:
            for k, v in ov_val.items():
                if v is None:
                    base_val.pop(k, None)
                elif isinstance(v, dict) and isinstance(base_val.get(k), dict):
                    base_val[k].update(v)
                else:
                    base_val[k] = v
            base_spec[key] = base_val
    else:
        base_spec[key] = ov_val


# FT4 (docs/design/flavour-boundary.md): a Flavour is deployment posture
# only. A Flavour-targeted overlay may patch these — anything else (llm,
# skills, mocking, prefer_local, infra_refs, tools/skills/memory of an agent,
# ...) is rejected the same way FlavourSeparationValidator rejects it on the
# base manifest, so an overlay can't reintroduce agent-spec / execution
# concerns through the back door.
_FLAVOUR_PATCH_KEYS: frozenset[str] = frozenset(
    {"agent_comm", "capabilities", "telemetry", "observability", "control", "tools", "config", "operator"}
)


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

    unknown = set(overlay_spec) - _FLAVOUR_PATCH_KEYS
    if unknown:
        raise OverlayTargetError(
            f"overlay patch for target.kind: Flavour contains non-deployment-posture "
            f"key(s) {sorted(unknown)!r} — see docs/design/flavour-boundary.md"
        )

    base_spec = merged.setdefault("spec", {})

    for key in ("observability", "control"):
        if key in overlay_spec:
            _merge_plugin_list_field(base_spec, overlay_spec, key)

    for key in ("agent_comm", "capabilities", "telemetry", "tools", "config", "operator"):
        if key not in overlay_spec:
            continue
        ov_val = overlay_spec[key]
        base_val = base_spec.get(key)
        if isinstance(ov_val, dict) and isinstance(base_val, dict):
            base_val.update(ov_val)
            base_spec[key] = base_val
        else:
            base_spec[key] = ov_val

    return merged


def merge_agent_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    if "spec" not in overlay:
        return merged

    overlay_spec = overlay["spec"]
    if "patch" in overlay_spec and isinstance(overlay_spec["patch"], dict):
        overlay_spec = overlay_spec["patch"]
    base_spec = merged.setdefault("spec", {})

    if "design_pattern" in overlay_spec:
        base_spec["design_pattern"] = overlay_spec["design_pattern"]

    if "context" in overlay_spec:
        ov_ctx = overlay_spec["context"]
        base_ctx = base_spec.get("context")
        if isinstance(ov_ctx, dict) and isinstance(base_ctx, dict):
            base_ctx.update(ov_ctx)
        elif isinstance(ov_ctx, dict) and base_ctx is None:
            base_spec["context"] = dict(ov_ctx)
        elif isinstance(ov_ctx, list):
            existing = list(base_ctx or []) if isinstance(base_ctx, list) else []
            existing.extend(ov_ctx)
            base_spec["context"] = existing
        else:
            base_spec["context"] = ov_ctx

    if "tools" in overlay_spec:
        existing_tools = list(base_spec.get("tools") or [])
        overlay_tools = list(overlay_spec["tools"] or [])
        existing_names = {t for t in existing_tools if isinstance(t, str)}
        for t in overlay_tools:
            if isinstance(t, str) and t in existing_names:
                continue
            existing_tools.append(t)
            if isinstance(t, str):
                existing_names.add(t)
        base_spec["tools"] = existing_tools

    if "capabilities" in overlay_spec:
        base_caps = base_spec.setdefault("capabilities", {})
        base_caps.update(overlay_spec["capabilities"])

    for key in ("skills_dir", "skills_include", "skills_exclude", "spec_tools"):
        if key in overlay_spec:
            base_spec[key] = overlay_spec[key]

    if "skills" in overlay_spec:
        existing_skills = list(base_spec.get("skills") or [])
        existing_set = set(existing_skills)
        for sk in overlay_spec["skills"] or []:
            if sk not in existing_set:
                existing_skills.append(sk)
                existing_set.add(sk)
        base_spec["skills"] = existing_skills

    if "tools_remove" in overlay_spec:
        existing = list(base_spec.get("tools_remove") or [])
        added = list(overlay_spec["tools_remove"] or [])
        seen: set[str] = set()
        merged_remove: list[str] = []
        for item in existing + added:
            if item not in seen:
                seen.add(item)
                merged_remove.append(item)
        base_spec["tools_remove"] = merged_remove

    if "plugins" in overlay_spec:
        existing_plugins = list(base_spec.get("plugins") or [])
        overlay_plugins = list(overlay_spec["plugins"] or [])
        name_to_idx: dict[str, int] = {}
        result_plugins = list(existing_plugins)
        for idx, existing_plugin in enumerate(result_plugins):
            key = existing_plugin.get("name") or existing_plugin.get("class_name", "")
            if key:
                name_to_idx[key] = idx
        for overlay_plugin in overlay_plugins:
            key = overlay_plugin.get("name") or overlay_plugin.get("class_name", "")
            if key and key in name_to_idx:
                result_plugins[name_to_idx[key]] = overlay_plugin
            else:
                result_plugins.append(overlay_plugin)
        base_spec["plugins"] = result_plugins

    if "memory" in overlay_spec:
        base_spec["memory"] = overlay_spec["memory"]

    if "memory_params" in overlay_spec:
        base_mp = base_spec.get("memory_params") or {}
        ov_mp = overlay_spec["memory_params"] or {}
        if isinstance(ov_mp, dict) and isinstance(base_mp, dict):
            base_mp.update(ov_mp)
            base_spec["memory_params"] = base_mp
        else:
            base_spec["memory_params"] = ov_mp

    if "memory_seed" in overlay_spec:
        existing_seed = list(base_spec.get("memory_seed") or [])
        existing_seed.extend(overlay_spec["memory_seed"] or [])
        base_spec["memory_seed"] = existing_seed

    if "infra_refs" in overlay_spec:
        existing = list(base_spec.get("infra_refs") or [])
        ov = overlay_spec["infra_refs"] or []
        if isinstance(ov, str):
            ov = [ov]
        for ref in ov:
            if ref not in existing:
                existing.append(ref)
        base_spec["infra_refs"] = existing

    if "llm" in overlay_spec:
        base_llm = base_spec.get("llm") or {}
        if isinstance(overlay_spec["llm"], dict) and isinstance(base_llm, dict):
            base_llm.update(overlay_spec["llm"])
            base_spec["llm"] = base_llm
        else:
            base_spec["llm"] = overlay_spec["llm"]

    if "observability" in overlay_spec:
        _merge_plugin_list_field(base_spec, overlay_spec, "observability")

    for block in ("execution", "control", "governance"):
        if block not in overlay_spec:
            continue
        base_block = base_spec.get(block) or {}
        ov_block = overlay_spec[block] or {}
        if isinstance(ov_block, dict):
            for k, v in ov_block.items():
                if v is None:
                    base_block.pop(k, None)
                elif k == "policies" and isinstance(v, list):
                    base_block["policies"] = list(v)
                elif isinstance(v, dict) and isinstance(base_block.get(k), dict):
                    base_block[k].update(v)
                else:
                    base_block[k] = v
            base_spec[block] = base_block
        else:
            base_spec[block] = ov_block

    if "context_manager" in overlay_spec:
        base_cm = base_spec.get("context_manager") or {}
        overlay_cm = overlay_spec["context_manager"]
        for cm_key, cm_val in overlay_cm.items():
            if isinstance(cm_val, list) and isinstance(base_cm.get(cm_key), list):
                seen = set(base_cm[cm_key])
                base_cm[cm_key] = list(base_cm[cm_key]) + [v for v in cm_val if v not in seen]
            else:
                base_cm[cm_key] = cm_val
        base_spec["context_manager"] = base_cm

    return merged


def merge_mas_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge MAS/App/Workflow overlay patch into base manifest."""
    merged = deepcopy(base)
    overlay_spec = overlay.get("spec") or {}
    patch = overlay_spec.get("patch") if isinstance(overlay_spec.get("patch"), dict) else overlay_spec
    if not isinstance(patch, dict) or not patch:
        return merged

    base_spec = merged.setdefault("spec", {})

    for key in ("agency", "workflow", "capabilities", "telemetry", "params", "intent"):
        if key not in patch:
            continue
        value = patch[key]
        if key in ("agency", "workflow") and isinstance(value, dict):
            base_spec[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(base_spec.get(key), dict):
            base_spec[key] = apply_merge_patch(deepcopy(base_spec[key]), value)
        else:
            base_spec[key] = deepcopy(value)

    # spec.patch.governance is a plugin list (e.g. [{sample_governance: {policies:
    # [...]}}]) meant to apply uniformly to every agent in the MAS — broadcast it
    # onto each agency-agent row so find_agency_entry/apply_agency_entry_overlay
    # (used for both the entry agent and every delegate, see
    # ctl/compose/backends/mas_runtime_py.py) can carry it into that agent's own
    # manifest spec, where parse_gov_spec/build_kernel_config wire it onto
    # KernelConfig.policy_engine.
    if "governance" in patch and isinstance(patch["governance"], list):
        agents_list = ((base_spec.get("agency") or {}).get("agents")) or base_spec.get("agents")
        if isinstance(agents_list, list):
            for entry in agents_list:
                if isinstance(entry, dict):
                    entry["governance"] = deepcopy(patch["governance"])

    global_dp = patch.get("design_pattern")
    overlay_agents = patch.get("agents")
    if isinstance(overlay_agents, dict):
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
                target["ref"] = per_agent["ref"]
            agent_spec = target.setdefault("spec", {})
            ctx = per_agent.get("context")
            if isinstance(ctx, dict):
                base_ctx = agent_spec.get("context")
                if isinstance(base_ctx, dict):
                    agent_spec["context"] = {**base_ctx, **deepcopy(ctx)}
                else:
                    agent_spec["context"] = deepcopy(ctx)
            for field in (
                "description",
                "design_pattern",
                "tools",
                "tools_remove",
                "skills",
                "memory",
                "plugins",
                "delegation",
            ):
                if field not in per_agent:
                    continue
                val = per_agent[field]
                if field == "delegation" and isinstance(val, dict):
                    base_del = (
                        agent_spec.get("delegation")
                        if isinstance(agent_spec.get("delegation"), dict)
                        else {}
                    )
                    agent_spec["delegation"] = {**base_del, **deepcopy(val)}
                elif field in ("description", "memory", "plugins"):
                    # Nested agent manifest spec (apply_agency_entry_overlay reads agent_spec)
                    agent_spec[field] = deepcopy(val)
                else:
                    # Top-level agency entry fields (apply_agency_entry_overlay checks entry + entry["spec"])
                    target[field] = deepcopy(val)
            if global_dp is not None and "design_pattern" not in per_agent:
                target["design_pattern"] = deepcopy(global_dp)
            if "memory_seed" in per_agent:
                existing_seed = list(agent_spec.get("memory_seed") or [])
                agent_spec["memory_seed"] = existing_seed + list(
                    deepcopy(per_agent["memory_seed"] or [])
                )

    if patch.get("agents_remove"):
        rm = {str(x) for x in patch["agents_remove"]}
        agency = base_spec.get("agency") or {}
        agents_list = agency.get("agents") or []
        agency["agents"] = [
            a for a in agents_list if not (isinstance(a, dict) and _agency_entry_key(a) in rm)
        ]
        base_spec["agency"] = agency

    if patch.get("agents_add"):
        agency = base_spec.setdefault("agency", {})
        existing = {
            _agency_entry_key(a)
            for a in agency.get("agents") or []
            if isinstance(a, dict) and _agency_entry_key(a) is not None
        }
        for entry in patch["agents_add"]:
            if not isinstance(entry, dict):
                continue
            key = _agency_entry_key(entry)
            if key is not None and key not in existing:
                agency.setdefault("agents", []).append(deepcopy(entry))
                existing.add(key)

    if global_dp is not None:
        agency_agents = (base_spec.get("agency") or {}).get("agents") or []
        spec_agents = base_spec.get("agents") or []
        for entry in list(agency_agents) + list(spec_agents):
            if isinstance(entry, dict) and "design_pattern" not in entry:
                entry["design_pattern"] = deepcopy(global_dp)

    return merged


def merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge an Agent, MAS, or Flavour patch overlay into a base manifest.

    Dispatch is by ``target.kind`` (falling back to the base manifest's own
    ``kind`` when the overlay doesn't declare one) — ``mas``/``app``/
    ``workflow`` -> :func:`merge_mas_overlay`, ``flavour`` ->
    :func:`merge_flavour_overlay`, everything else -> :func:`merge_agent_overlay`.
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
        and isinstance(spec.get("patch"), dict)
    )
    if not canonical:
        overlay = normalize_overlay(overlay, name=str((overlay.get("metadata") or {}).get("name") or "overlay"))

    target_kind = str((overlay.get("spec") or {}).get("target", {}).get("kind", "")).lower()
    base_kind = str(base.get("kind", "")).lower()
    if target_kind in ("mas", "app", "workflow") or base_kind in ("mas", "app", "workflow"):
        return merge_mas_overlay(base, overlay)
    if target_kind == "flavour" or base_kind == "flavour":
        return merge_flavour_overlay(base, overlay)

    return merge_agent_overlay(base, overlay)
