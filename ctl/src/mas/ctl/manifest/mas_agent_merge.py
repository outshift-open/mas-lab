#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Merge MAS workflow onto the entry agent manifest at run-mas bootstrap."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from mas.ctl.manifest.spec_bindings import parse_collaboration
from mas.runtime.boundary.context.manifest_context import routing_description_from_agent
from mas.runtime.boundary.delegation.completion import peer_completion_checks_from_manifests
from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator
from mas.runtime.boundary.delegation.policy import delegation_targets
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.tools import resolve_manifest_tool_refs

logger = logging.getLogger(__name__)

RunTurnFn = Callable[[str, str], str]


from mas.runtime.engine.leaf import leaf_engine


def _load_agent_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else None


def _tool_ref_key(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("ref") or item.get("name") or "")
    return str(item)


def _merge_tool_ref_list(existing: list[Any], added: list[Any]) -> list[Any]:
    out = list(existing)
    seen = {_tool_ref_key(t) for t in out if _tool_ref_key(t)}
    for item in added:
        key = _tool_ref_key(item)
        if not key:
            logger.warning(
                "tool list entry has no ref/name; merging without dedup key: %r",
                item,
            )
            out.append(copy.deepcopy(item))
            continue
        if key not in seen:
            out.append(copy.deepcopy(item))
            seen.add(key)
    return out


def _agency_entries_by_id(mas_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index agency/spec.agents rows by id or name.

    ``spec.agency.agents`` is consulted before ``spec.agents``; the first row
    for a given id wins when both lists declare the same agent.
    """
    spec = mas_config.get("spec") or mas_config
    buckets = [
        (spec.get("agency") or {}).get("agents") or [],
        spec.get("agents") or [],
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for agents in buckets:
        for entry in agents:
            if not isinstance(entry, dict):
                continue
            aid = str(entry.get("id") or entry.get("name") or "")
            if aid and aid not in by_id:
                by_id[aid] = entry
    return by_id


def find_agency_entry(mas_config: dict[str, Any] | None, agent_id: str) -> dict[str, Any] | None:
    """Return the agency/spec.agents list row for *agent_id*, if present."""
    if not mas_config or not agent_id:
        return None
    return _agency_entries_by_id(mas_config).get(agent_id)


def _entry_val(entry: dict[str, Any], entry_spec: dict[str, Any], field: str) -> Any:
    val = entry.get(field)
    return val if val is not None else entry_spec.get(field)


def _apply_description_overlay(
    spec: dict[str, Any],
    agency_entry: dict[str, Any],
    entry_spec: dict[str, Any],
) -> None:
    description = _entry_val(agency_entry, entry_spec, "description")
    if isinstance(description, str) and description.strip():
        spec["description"] = description.strip()


def apply_agency_entry_overlay(
    agent_manifest: dict[str, Any],
    agency_entry: dict[str, Any],
) -> dict[str, Any]:
    """Merge per-agent MAS overlay fields onto a loaded agent manifest."""
    out = copy.deepcopy(agent_manifest)
    spec = out.setdefault("spec", {})
    entry_spec = agency_entry.get("spec") or {}
    if not isinstance(entry_spec, dict):
        entry_spec = {}

    ctx = entry_spec.get("context")
    if isinstance(ctx, dict) and ctx:
        base_ctx = spec.get("context")
        if isinstance(base_ctx, dict):
            for key, ov in ctx.items():
                if (bv := base_ctx.get(key)) is not None and type(bv) is not type(ov):
                    logger.warning(
                        "agency overlay context[%r] type %s overrides base type %s",
                        key,
                        type(ov).__name__,
                        type(bv).__name__,
                    )
            spec["context"] = {**base_ctx, **copy.deepcopy(ctx)}
        else:
            spec["context"] = copy.deepcopy(ctx)

    _apply_description_overlay(spec, agency_entry, entry_spec)

    for field in ("tools", "tools_remove"):
        val = _entry_val(agency_entry, entry_spec, field)
        if val:
            spec[field] = _merge_tool_ref_list(list(spec.get(field) or []), list(val))

    for field in ("design_pattern", "skills", "memory", "plugins"):
        if (val := _entry_val(agency_entry, entry_spec, field)) is not None:
            spec[field] = copy.deepcopy(val)

    memory_seed = _entry_val(agency_entry, entry_spec, "memory_seed")
    if memory_seed:
        existing_seed = list(spec.get("memory_seed") or [])
        spec["memory_seed"] = existing_seed + list(copy.deepcopy(memory_seed))

    return out


def apply_agency_routing_overlay(
    agent_manifest: dict[str, Any],
    agency_entry: dict[str, Any],
) -> dict[str, Any]:
    """Merge agency fields used for delegation routing (description, completion_check)."""
    out = copy.deepcopy(agent_manifest)
    spec = out.setdefault("spec", {})
    entry_spec = agency_entry.get("spec") or {}
    if not isinstance(entry_spec, dict):
        entry_spec = {}

    _apply_description_overlay(spec, agency_entry, entry_spec)

    delegation = _entry_val(agency_entry, entry_spec, "delegation")
    if isinstance(delegation, dict) and delegation:
        base_del = spec.get("delegation") if isinstance(spec.get("delegation"), dict) else {}
        spec["delegation"] = {**base_del, **copy.deepcopy(delegation)}

    return out


def _peer_manifests_for_ids(
    mas_config: dict[str, Any],
    *,
    mas_base_dir: Path,
    peer_ids: list[str],
) -> dict[str, dict[str, Any]]:
    by_id = _agency_entries_by_id(mas_config)
    out: dict[str, dict[str, Any]] = {}
    for peer_id in peer_ids:
        entry = by_id.get(peer_id)
        if not entry:
            continue
        ref = entry.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            continue
        path = (mas_base_dir / ref).resolve()
        peer_manifest = _load_agent_yaml(path)
        if peer_manifest is None:
            logger.warning("peer agent %r manifest not found: %s", peer_id, path)
            continue
        out[peer_id] = apply_agency_routing_overlay(peer_manifest, entry)
    return out


def enrich_entry_agent_for_delegation(
    agent_manifest: dict[str, Any],
    mas_config: dict[str, Any],
    *,
    manifest_dir: Path | None = None,
    mas_base_dir: Path | None = None,
) -> dict[str, Any]:
    """Attach MAS ``workflow`` to the entry agent; resolve tool refs and peer descriptions."""
    spec = agent_manifest.get("spec") or {}
    parse_collaboration(spec.get("collaboration"))
    out = copy.deepcopy(agent_manifest)
    mas_spec = mas_config.get("spec", mas_config) if isinstance(mas_config, dict) else {}
    wf = mas_spec.get("workflow")
    if isinstance(wf, dict):
        spec_out = out.setdefault("spec", {})
        if spec_out.get("workflow") and spec_out.get("workflow") != wf:
            logger.warning(
                "entry agent spec.workflow replaced by MAS workflow (MAS topology wins)"
            )
        spec_out["workflow"] = copy.deepcopy(wf)
    if manifest_dir is not None:
        resolve_manifest_tool_refs(out, manifest_dir, inplace=True)
    return out


def wire_entry_engine_delegation(
    engine: Any,
    manifest: dict[str, Any],
    manifest_dir: Path,
    *,
    run_turn: RunTurnFn,
    entry_agent_id: str,
    mas_config: dict[str, Any] | None = None,
    mas_base_dir: Path | None = None,
) -> None:
    """Set enriched manifest on the entry engine and bind ``LlmDelegator`` when peers exist.

    When peers exist, ``use_tool_loop`` is enabled on the leaf engine so the LLM can
    emit ``delegate_to_*`` tool calls. A manifest or instantiation that set
    ``use_tool_loop=False`` is overridden with a warning.
    """
    if engine is None:
        return
    leaf = leaf_engine(engine)
    leaf.manifest = manifest
    if isinstance(leaf, LiveLlmEngine):
        leaf.manifest_dir = manifest_dir
    peers = delegation_targets(manifest, agent_id=entry_agent_id)
    peer_manifests: dict[str, dict[str, Any]] = {}
    if isinstance(leaf, LiveLlmEngine) and peers and mas_config is not None and mas_base_dir is not None:
        peer_manifests = _peer_manifests_for_ids(
            mas_config, mas_base_dir=mas_base_dir, peer_ids=peers
        )
        leaf.delegation_peer_descriptions = {
            peer_id: desc
            for peer_id, manifest_doc in peer_manifests.items()
            if (desc := routing_description_from_agent(manifest_doc))
        }
    elif isinstance(leaf, LiveLlmEngine):
        leaf.delegation_peer_descriptions = None
    if not peers:
        leaf.delegation = None
        return
    peer_completion_checks = (
        peer_completion_checks_from_manifests(peer_manifests) if peer_manifests else None
    )
    leaf.delegation = LlmDelegator(
        run_turn=run_turn,
        peer_completion_checks=peer_completion_checks,
    )
    if hasattr(leaf, "use_tool_loop"):
        if not leaf.use_tool_loop:
            logger.warning(
                "entry agent %r: enabling use_tool_loop for dynamic delegation (%d peers)",
                entry_agent_id,
                len(peers),
            )
            leaf.use_tool_loop = True


def reset_engine_delegation(engine: Any) -> None:
    """Clear delegate caches at the start of each user turn."""
    while engine is not None:
        delegation = getattr(engine, "delegation", None)
        reset_fn = getattr(delegation, "reset_session", None)
        if callable(reset_fn):
            reset_fn()
        engine = getattr(engine, "inner", None)
