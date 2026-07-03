#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""MAS manifest loading for mas-lab bench — compose + agent resolution."""


from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mas.ctl.compose.runner import ComposeRequest, compose_run
from mas.ctl.overlay import apply_merge_patch
from mas.ctl.runtime_cli import load_merged_agent_manifest
from mas.ctl.validate import validate_file, validation_enabled
from mas.runtime.spec.source import load_yaml_mapping, resolve_yaml_path


@dataclass
class LoadedMAS:
    """Materialized MAS config (runtime dict) for bench compatibility."""

    _raw: dict[str, Any]
    path: Path


def _entry_agent_id(mas: dict[str, Any]) -> str:
    spec = mas.get("spec") or mas
    if isinstance(spec.get("entry_agent"), str):
        return spec["entry_agent"]
    wf = spec.get("workflow") or {}
    if isinstance(wf, dict) and wf.get("entry"):
        return str(wf["entry"])
    agency = spec.get("agency") or {}
    agents = agency.get("agents") or []
    if agents and isinstance(agents[0], dict):
        return str(agents[0].get("id") or agents[0].get("name") or "agent")
    agents_list = mas.get("agents") or []
    if agents_list and isinstance(agents_list[0], dict):
        return str(agents_list[0].get("id") or agents_list[0].get("name") or "agent")
    return "agent"


def _agent_path_for_entry(mas: dict[str, Any], mas_path: Path, entry_id: str) -> Path:
    spec = mas.get("spec") or mas
    agency = spec.get("agency") or {}
    base = mas_path.parent
    for entry in agency.get("agents") or []:
        if not isinstance(entry, dict):
            continue
        aid = str(entry.get("id") or entry.get("name") or "")
        if aid and aid != entry_id:
            continue
        ref = entry.get("ref")
        if ref:
            return resolve_yaml_path(str(ref), base)
    for ref in (f"agents/{entry_id}.yaml", f"{entry_id}.yaml", "agent.yaml"):
        try:
            return resolve_yaml_path(ref, base)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(f"agent manifest for entry {entry_id!r} not found near {mas_path}")


def _agent_runtime_dict(doc: dict[str, Any], *, agent_id: str, agent_dir: Path) -> dict[str, Any]:
    meta = doc.get("metadata") or {}
    spec = doc.get("spec") or {}
    dp = spec.get("design_pattern") or {}
    models = spec.get("models") or []
    raw: dict[str, Any] = {
        "id": agent_id,
        "name": meta.get("name") or agent_id,
        "pattern_framework": dp.get("type", "react"),
        "pattern_params": dp.get("config") or dp.get("params") or {},
        "has_design_pattern": bool(dp),
        "_agent_dir": str(agent_dir),
    }
    if models:
        raw["llm_model"] = models[0].get("model") if isinstance(models[0], dict) else None
    if spec.get("tools"):
        raw["spec_tools"] = spec["tools"]
    return raw


def load_mas_config(
    mas_path: Path,
    *,
    overlay_paths: list[Path] | None = None,
    validate: bool = False,
) -> LoadedMAS:
    """Load mas.yaml via compose; expand agency refs into runtime ``_raw`` dict."""
    doc = load_yaml_mapping(mas_path)
    if str((doc or {}).get("kind", "")).lower() == "agent":
        return _loaded_mas_from_agent(mas_path, doc or {})

    if validate and validation_enabled():
        validate_file(mas_path, kind="mas").raise_if_failed()
    result = compose_run(
        ComposeRequest(
            manifest=mas_path,
            overlay_paths=list(overlay_paths or []),
            validate=validate,
        )
    )
    mas = result.mas_config
    base_dir = mas_path.parent
    raw_agents: list[dict[str, Any]] = []
    entry_id = _entry_agent_id(mas)
    spec = mas.get("spec") or mas
    agency = spec.get("agency") or {}
    for entry in agency.get("agents") or []:
        if not isinstance(entry, dict):
            continue
        if "ref" in entry:
            ap = resolve_yaml_path(str(entry["ref"]), base_dir)
            agent_doc, _ = load_merged_agent_manifest(ap, validate=False)
            aid = str(entry.get("id") or (agent_doc or {}).get("metadata", {}).get("name") or ap.stem)
            raw_agents.append(_agent_runtime_dict(agent_doc or {}, agent_id=aid, agent_dir=ap.parent))
        elif entry.get("kind", "").lower() == "agent" or "metadata" in entry:
            aid = str(entry.get("metadata", {}).get("name") or entry.get("id") or "agent")
            raw_agents.append(_agent_runtime_dict(entry, agent_id=aid, agent_dir=base_dir))

    if not raw_agents and str(mas.get("kind", "")).lower() == "agent":
        raw_agents.append(_agent_runtime_dict(mas, agent_id=entry_id, agent_dir=base_dir))

    raw = {
        "mas": {
            "id": mas.get("metadata", {}).get("name") or mas_path.stem,
            "version": mas.get("metadata", {}).get("version", "0.1.0"),
            "description": mas.get("metadata", {}).get("description", ""),
            "entry_agent": entry_id,
        },
        "agents": raw_agents,
        "workflow": spec.get("workflow") or {},
        "capabilities": spec.get("capabilities") or {},
    }
    return LoadedMAS(_raw=raw, path=mas_path)


def _loaded_mas_from_agent(agent_path: Path, doc: dict[str, Any]) -> LoadedMAS:
    base_dir = agent_path.parent
    entry_id = str((doc.get("metadata") or {}).get("name") or agent_path.stem)
    agent_row = _agent_runtime_dict(doc, agent_id=entry_id, agent_dir=base_dir)
    raw = {
        "mas": {
            "id": entry_id,
            "version": (doc.get("metadata") or {}).get("version", "0.1.0"),
            "description": (doc.get("metadata") or {}).get("description", ""),
            "entry_agent": entry_id,
        },
        "agents": [agent_row],
        "workflow": {
            "type": "dynamic",
            "entry": entry_id,
            "nodes": [{"id": entry_id, "role": "specialist"}],
        },
        "capabilities": (doc.get("spec") or {}).get("capabilities") or {},
    }
    return LoadedMAS(_raw=raw, path=agent_path)


def load_agent_for_bench(
    mas_path: Path,
    overlay_paths: list[Path] | None = None,
    *,
    validate: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Return agent manifest dict + path for MasBenchRunner / SessionController."""
    doc = load_yaml_mapping(mas_path)
    if str((doc or {}).get("kind", "")).lower() == "agent":
        overlays = tuple(str(p) for p in (overlay_paths or []))
        agent, _ = load_merged_agent_manifest(
            mas_path,
            overlays=overlays,
            validate=validate,
            manifest_dir=mas_path.parent.parent
            if mas_path.parent.name == "agents"
            else mas_path.parent,
        )
        return agent or {}, mas_path

    overlays = tuple(str(p) for p in (overlay_paths or []))
    result = compose_run(
        ComposeRequest(
            manifest=mas_path,
            overlay_paths=list(overlay_paths or []),
            validate=validate,
        )
    )
    entry = _entry_agent_id(result.mas_config)
    agent_path = _agent_path_for_entry(result.mas_config, mas_path, entry)
    agent, _ = load_merged_agent_manifest(
        agent_path,
        overlays=overlays,
        validate=validate,
        manifest_dir=mas_path.parent,
    )
    return agent or {}, agent_path


def load_overlay_as_spec(overlay_path: Path, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge overlay patch into sibling mas.yaml (legacy check-run helper)."""
    overlay_path = Path(overlay_path)
    ov = overlay if overlay is not None else load_yaml_mapping(overlay_path)
    candidates = [
        overlay_path.parent.parent / "mas.yaml",
        overlay_path.parent / "mas.yaml",
    ]
    mas_yaml = next((c for c in candidates if c.is_file()), None)
    if mas_yaml is None:
        raise FileNotFoundError(f"overlay {overlay_path.name}: no sibling mas.yaml")
    spec = dict(load_mas_config(mas_yaml, validate=False)._raw)
    patch = (ov.get("spec") or {}).get("patch") or {}
    if patch:
        apply_merge_patch(spec, patch)
    return spec


def load_agent_runtime_entry(agent_path: Path, *, agent_id: str | None = None) -> dict[str, Any]:
    """Expand an agent YAML path into a bench runtime agent row."""
    doc, _ = load_merged_agent_manifest(agent_path, validate=False)
    aid = agent_id or (doc or {}).get("metadata", {}).get("name") or agent_path.stem
    return _agent_runtime_dict(doc or {}, agent_id=str(aid), agent_dir=agent_path.parent)
