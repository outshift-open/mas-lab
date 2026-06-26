#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agent overlay merge — ported from mas-lab runtime/manifest/composition.py (RFC 7396 + agent rules)."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


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
        ov_obs = overlay_spec["observability"]
        if isinstance(ov_obs, list):
            # List replaces base (mas-lab parity)
            base_spec["observability"] = list(ov_obs)
        elif isinstance(ov_obs, dict):
            base_obs = base_spec.get("observability") or {}
            if isinstance(base_obs, list):
                base_spec["observability"] = ov_obs
            else:
                for k, v in ov_obs.items():
                    if v is None:
                        base_obs.pop(k, None)
                    elif isinstance(v, dict) and isinstance(base_obs.get(k), dict):
                        base_obs[k].update(v)
                    else:
                        base_obs[k] = v
                base_spec["observability"] = base_obs
        else:
            base_spec["observability"] = ov_obs

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

    overlay_agents = patch.get("agents")
    if isinstance(overlay_agents, dict):
        agency = base_spec.setdefault("agency", {})
        agents_list = list(agency.get("agents") or [])
        by_id = {
            str(a.get("id")): a for a in agents_list if isinstance(a, dict) and a.get("id")
        }
        for agent_id, per_agent in overlay_agents.items():
            if not isinstance(per_agent, dict):
                continue
            target = by_id.get(str(agent_id))
            if target is None:
                continue
            if "ref" in per_agent:
                target["ref"] = per_agent["ref"]
            role = per_agent.get("role")
            if isinstance(role, dict) and role.get("instructions"):
                target.setdefault("role", {})["instructions"] = role["instructions"]
            for field in ("design_pattern", "tools", "tools_remove", "skills"):
                if field in per_agent:
                    target[field] = deepcopy(per_agent[field])
        agency["agents"] = list(by_id.values()) if by_id else agents_list

    if patch.get("agents_remove"):
        rm = set(patch["agents_remove"])
        agency = base_spec.get("agency") or {}
        agents_list = agency.get("agents") or []
        agency["agents"] = [a for a in agents_list if a.get("id") not in rm]
        base_spec["agency"] = agency

    if patch.get("agents_add"):
        agency = base_spec.setdefault("agency", {})
        existing = {a.get("id") for a in agency.get("agents") or []}
        for entry in patch["agents_add"]:
            if isinstance(entry, dict) and entry.get("id") not in existing:
                agency.setdefault("agents", []).append(deepcopy(entry))

    return merged


def merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge agent or MAS patch overlay into base manifest."""
    from mas.ctl.overlay.normalize import normalize_overlay

    if "spec" not in overlay:
        base_kind = str(base.get("kind", "")).lower()
        if base_kind in ("mas", "app", "workflow"):
            return merge_mas_overlay(base, overlay)
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

    return merge_agent_overlay(base, overlay)
