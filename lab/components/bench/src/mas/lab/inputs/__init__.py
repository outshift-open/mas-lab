#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Run Input Envelope — per-run inputs for bench / ctl (envelope-only)."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.runtime.spec.source import load_yaml_file


def _resolve_seeds(
    seeds_val: Optional[str | list],
    base_path: Optional[Path] = None,
) -> Optional[List[Dict[str, Any]]]:
    if seeds_val is None:
        return None
    if isinstance(seeds_val, list):
        return seeds_val or None
    if isinstance(seeds_val, str):
        seed_path = Path(seeds_val)
        if base_path and not seed_path.is_absolute():
            seed_path = base_path / seed_path
        data = load_yaml_file(seed_path)
        if isinstance(data, list):
            return data or None
        if isinstance(data, dict):
            for key in ("seeds", "items", "memory_seeds", "entries"):
                if key in data:
                    val = data[key]
                    return val if isinstance(val, list) else None
        return None
    raise TypeError(f"memory_seeds must be list or path string, got {type(seeds_val)}")


def _resolve_fixture(
    fixture_val: Any,
    base_path: Optional[Path] = None,
) -> Any:
    if fixture_val is None or isinstance(fixture_val, (dict, list)):
        return fixture_val
    if isinstance(fixture_val, str):
        fix_path = Path(fixture_val)
        if base_path and not fix_path.is_absolute():
            fix_path = base_path / fix_path
        return load_yaml_file(fix_path)
    raise TypeError(f"tool_fixtures must be dict, list, or path string")


@dataclass
class RunInput:
    user: List[Dict[str, str]]
    hitl: List[Dict[str, str]] = field(default_factory=list)
    memory_seeds: Optional[List[Dict[str, Any]]] = None
    tool_fixtures: Any = None
    checkpoint_load: Any = None
    checkpoint_save: Any = False
    session_id: Optional[str] = None
    expectations: Dict[str, Any] = field(default_factory=dict)

    @property
    def primary_prompt(self) -> str:
        return str(self.user[0]["content"]) if self.user else ""

    def all_user_turns(self) -> List[Dict[str, str]]:
        """User messages after the initial prompt (multi-turn)."""
        return self.user[1:] if len(self.user) > 1 else []

    def scripted_queries(self) -> List[str]:
        """Ordered user + HITL messages for SessionController."""
        queries: List[str] = []
        for msg in self.user:
            content = msg.get("content")
            if content:
                queries.append(str(content))
        for msg in self.hitl:
            content = msg.get("content")
            if content:
                queries.append(str(content))
        return queries


def _deep_merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _scenario_block(scenario: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not scenario:
        return {}
    block: Dict[str, Any] = {}
    if isinstance(scenario.get("inputs"), dict):
        block["inputs"] = dict(scenario["inputs"])
    if isinstance(scenario.get("expectations"), dict):
        block["expectations"] = dict(scenario["expectations"])
    spec = scenario.get("spec") or {}
    if spec.get("memory_seed") is not None:
        block.setdefault("inputs", {})["memory_seeds"] = spec["memory_seed"]
    return block


def _experiment_defaults(experiment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not experiment:
        return {}
    spec = experiment.get("spec") or experiment
    defaults = spec.get("defaults") or {}
    out: Dict[str, Any] = {}
    if isinstance(defaults.get("inputs"), dict):
        out["inputs"] = dict(defaults["inputs"])
    if isinstance(defaults.get("expectations"), dict):
        out["expectations"] = dict(defaults["expectations"])
    return out


def load_run_input(
    item: Dict[str, Any],
    *,
    scenario: Optional[Dict[str, Any]] = None,
    experiment: Optional[Dict[str, Any]] = None,
    base_path: Optional[Path] = None,
) -> RunInput:
    """Merge experiment → scenario → item envelope into :class:`RunInput`."""
    if "inputs" not in item:
        raise ValueError(
            f"dataset item {item.get('id')!r} missing required 'inputs' block "
            "(run scripts/migrate_dataset_envelope.py)"
        )
    merged: Dict[str, Any] = {}
    merged = _deep_merge_dict(merged, _experiment_defaults(experiment))
    merged = _deep_merge_dict(merged, _scenario_block(scenario))
    merged = _deep_merge_dict(
        merged,
        {
            "inputs": dict(item["inputs"]),
            "expectations": dict(item.get("expectations") or {}),
        },
    )

    inputs = merged["inputs"]
    if not inputs.get("user"):
        raise ValueError(f"item {item.get('id')!r}: inputs.user is required")

    memory_raw = inputs.get("memory_seeds")
    memory_seeds = _resolve_seeds(memory_raw, base_path) if memory_raw is not None else None
    tool_fixtures = (
        _resolve_fixture(inputs.get("tool_fixtures"), base_path)
        if inputs.get("tool_fixtures") is not None
        else None
    )

    checkpoint = inputs.get("checkpoint") or {}
    if isinstance(checkpoint, dict):
        checkpoint_load = checkpoint.get("load")
        checkpoint_save = checkpoint.get("save", False)
    else:
        checkpoint_load = checkpoint
        checkpoint_save = False

    return RunInput(
        user=list(inputs["user"]),
        hitl=list(inputs.get("hitl") or []),
        memory_seeds=memory_seeds,
        tool_fixtures=tool_fixtures,
        checkpoint_load=checkpoint_load,
        checkpoint_save=checkpoint_save,
        session_id=inputs.get("session_id"),
        expectations=dict(merged.get("expectations") or {}),
    )


def run_input_to_dict(run_input: RunInput) -> Dict[str, Any]:
    inputs: Dict[str, Any] = {"user": run_input.user}
    if run_input.hitl:
        inputs["hitl"] = run_input.hitl
    if run_input.memory_seeds is not None:
        inputs["memory_seeds"] = run_input.memory_seeds
    if run_input.tool_fixtures is not None:
        inputs["tool_fixtures"] = run_input.tool_fixtures
    if run_input.session_id:
        inputs["session_id"] = run_input.session_id
    if run_input.checkpoint_load is not None or run_input.checkpoint_save:
        inputs["checkpoint"] = {
            "load": run_input.checkpoint_load,
            "save": run_input.checkpoint_save,
        }
    out: Dict[str, Any] = {"inputs": inputs}
    if run_input.expectations:
        out["expectations"] = run_input.expectations
    return out


def fingerprint_run_input(run_input: RunInput) -> str:
    """Stable hash for trace-cache ``inputs.json``."""
    payload = json.dumps(run_input_to_dict(run_input), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_run_input_envelope(data: Dict[str, Any]) -> None:
    import jsonschema

    from mas.lab.schemas.paths import lab_schema_dir

    schema = load_yaml_file(lab_schema_dir() / "run-input.schema.yaml")
    jsonschema.Draft7Validator(schema).validate(data)
