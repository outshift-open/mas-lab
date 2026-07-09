#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest JSON Schema loader — schemas live under docs/schemas/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_ROOT = Path(__file__).resolve().parents[5] / "docs" / "schemas"

_KIND_MAP: dict[str, str] = {
    "agent": "runtime/agent.schema.yaml",
    "mas": "runtime/mas.schema.yaml",
    "overlay": "runtime/overlay.schema.yaml",
    "infra": "runtime/infra.schema.yaml",
    "flavour": "runtime/flavour.schema.yaml",
    "workflow": "runtime/workflow.schema.yaml",
    "tool": "runtime/tool.schema.yaml",
    "tool_bundle": "runtime/tool_bundle.schema.yaml",
    "prompt_bundle": "runtime/prompt_bundle.schema.yaml",
    "deployment": "deployment.schema.yaml",
    "runtime_profile": "runtime-profile.schema.yaml",
    "runtime-profile": "runtime-profile.schema.yaml",
    "memory_seed": "memory-seed.schema.yaml",
    "memory-seed": "memory-seed.schema.yaml",
    "checkpoint": "checkpoint.schema.yaml",
    "effective_bind": "effective-bind.schema.yaml",
    "effective-bind": "effective-bind.schema.yaml",
    "placement_plan": "placement-plan.schema.yaml",
    "experiment": "lab/experiment.schema.yaml",
    "dataset": "lab/dataset.schema.yaml",
    "pipeline": "lab/pipeline.schema.yaml",
    "library": "library.schema.yaml",
}

_YAML_KIND: dict[str, str] = {
    "Agent": "agent",
    "MAS": "mas",
    "Overlay": "overlay",
    "Workflow": "workflow",
    "Flavour": "flavour",
    "Tool": "tool",
    "PromptBundle": "prompt_bundle",
    "ToolBundle": "tool_bundle",
    "Deployment": "deployment",
    "RuntimeProfile": "runtime_profile",
    "PlacementPlan": "placement_plan",
    "MemorySeed": "memory_seed",
    "InfraBundle": "infra",
    "InfraMiddleware": "infra",
    "InfraInterceptor": "infra",
    "LLMProxy": "infra",
    "LLMLocal": "infra",
    "ToolServerRegistry": "infra",
    "PersonalSecrets": "infra",
    "Application": "infra",
    "ToolRegistry": "infra",
    "ToolProvider": "infra",
    "Datastore": "infra",
    "SecretsProvider": "infra",
    "Infrastructure": "infra",
    "Library": "library",
}


def schema_root() -> Path:
    return _SCHEMA_ROOT


def declared_kind(data: dict) -> str | None:
    """Return manifest kind from explicit document shape only — no heuristics."""
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("experiment"), dict):
        return "experiment"
    if isinstance(data.get("pipeline"), dict):
        return "pipeline"
    if isinstance(data.get("lab"), dict):
        return "lab-config"
    explicit = data.get("kind")
    if isinstance(explicit, str):
        mapped = _YAML_KIND.get(explicit, explicit.lower())
        if mapped in _KIND_MAP or schema_path_for_kind(mapped) is not None:
            return mapped
        if explicit == "Dataset":
            return "dataset"
    return None


def infer_kind(data: dict) -> str | None:
    """Alias for :func:`declared_kind` (explicit manifest shape only)."""
    return declared_kind(data)


def schema_path_for_kind(kind: str) -> Path | None:
    rel = _KIND_MAP.get(kind.lower().replace("-", "_"))
    if rel is None:
        return None
    path = _SCHEMA_ROOT / rel
    return path if path.exists() else None


@lru_cache(maxsize=32)
def load_schema(kind: str) -> dict:
    path = schema_path_for_kind(kind)
    if path is None:
        raise KeyError(f"no schema registered for kind: {kind}")
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _resolve_local_refs(raw, path.parent)


def _resolve_local_refs(node: Any, base_dir: Path) -> Any:
    """Inline ``./`` JSON Schema refs so validation does not depend on ``$id`` URIs."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("./"):
            frag_path = (base_dir / ref[2:]).resolve()
            with frag_path.open(encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh)
            return _resolve_local_refs(loaded, frag_path.parent)
        return {k: _resolve_local_refs(v, base_dir) for k, v in node.items() if k != "$ref" or not isinstance(ref, str) or not ref.startswith("./")}
    if isinstance(node, list):
        return [_resolve_local_refs(item, base_dir) for item in node]
    return node


def list_schema_kinds() -> list[str]:
    return sorted(_KIND_MAP.keys())
