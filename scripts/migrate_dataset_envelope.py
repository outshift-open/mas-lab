#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""One-shot migration: flat dataset items → inputs/expectations envelope."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

LEGACY_ITEM_KEYS = frozenset(
    {
        "prompt",
        "turns",
        "memory_seeds",
        "session_id",
        "expected_answer",
        "ground_truth",
        "expected_governance",
        "trigger",
        "expected_cost_range",
        "hitl_responses",
    }
)


def _migrate_item(item: dict) -> dict:
    if "inputs" in item:
        if any(k in item for k in LEGACY_ITEM_KEYS):
            raise ValueError(f"item {item.get('id')!r} mixes envelope and legacy fields")
        return item

    user: list[dict] = []
    hitl: list[dict] = []
    if "prompt" in item:
        user.append({"role": "user", "content": str(item["prompt"])})
    for turn in item.get("turns") or []:
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", ""))
        msg = {"role": role, "content": content}
        if role == "hitl":
            hitl.append(msg)
        else:
            user.append(msg)
    if not user:
        raise ValueError(f"item {item.get('id')!r} has no prompt/user messages")

    inputs: dict = {"user": user}
    if hitl:
        inputs["hitl"] = hitl
    if item.get("memory_seeds") is not None:
        inputs["memory_seeds"] = item["memory_seeds"]
    if item.get("session_id"):
        inputs["session_id"] = item["session_id"]

    expectations: dict = {}
    gt = item.get("ground_truth") or item.get("expected_answer")
    if gt is not None:
        expectations["ground_truth"] = gt
    gov: dict = {}
    if item.get("expected_governance"):
        gov["expected"] = item["expected_governance"]
    if item.get("trigger"):
        gov["trigger"] = item["trigger"]
    if item.get("expected_cost_range") is not None:
        gov["expected_cost_range"] = item["expected_cost_range"]
    if item.get("hitl_responses"):
        gov["hitl_responses"] = item["hitl_responses"]
    if gov:
        expectations["governance"] = gov

    out: dict = {"id": item["id"], "inputs": inputs}
    if expectations:
        out["expectations"] = expectations

    passthrough = {
        "category",
        "group",
        "type",
        "tags",
        "metadata",
        "target_agents",
        "conversation_id",
    }
    for key in passthrough:
        if key in item:
            out[key] = item[key]
    return out


def _migrate_items(items: list) -> list:
    return [_migrate_item(dict(i)) for i in items]


def _migrate_yaml(path: Path) -> bool:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return False
    changed = False
    if data.get("kind") == "Dataset" and isinstance(data.get("spec"), dict):
        items = data["spec"].get("items")
        if isinstance(items, list) and items:
            data["spec"]["items"] = _migrate_items(items)
            changed = True
    elif isinstance(data.get("items"), list):
        data["items"] = _migrate_items(data["items"])
        changed = True
    if changed:
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
            encoding="utf-8",
        )
    return changed


def _migrate_json(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return False
    data["items"] = _migrate_items(items)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def _migrate_experiment_overlays(path: Path) -> bool:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return False
    exp = data.get("experiment") or data
    scenarios = exp.get("scenarios")
    if not isinstance(scenarios, list):
        return False
    changed = False
    for sc in scenarios:
        if not isinstance(sc, dict):
            continue
        ov = sc.get("overlays")
        if ov is None:
            continue
        if isinstance(ov, list):
            sc["overlays"] = {"logic": list(ov), "control": [], "infra": []}
            changed = True
        elif isinstance(ov, dict) and not any(k in ov for k in ("logic", "control", "infra")):
            raise ValueError(f"{path}: invalid overlays dict in scenario {sc.get('id')}")
    if changed:
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
            encoding="utf-8",
        )
    return changed


def main() -> int:
    patterns = [
        "library-samples/datasets/**/*.yaml",
        "library-samples/datasets/**/*.json",
        "labs/**/datasets/**/*.yaml",
        "docs/tutorials/**/dataset*.yaml",
        "tests/fixtures/**/dataset.yaml",
    ]
    exp_patterns = [
        "labs/**/experiment*.yaml",
        "docs/tutorials/**/experiment*.yaml",
        "tests/fixtures/**/experiment.yaml",
    ]
    n = 0
    for pat in patterns:
        for path in sorted(ROOT.glob(pat)):
            if path.is_symlink():
                continue
            if path.suffix == ".yaml":
                if _migrate_yaml(path):
                    print(f"migrated dataset {path.relative_to(ROOT)}")
                    n += 1
            elif path.suffix == ".json":
                if _migrate_json(path):
                    print(f"migrated dataset {path.relative_to(ROOT)}")
                    n += 1
    for pat in exp_patterns:
        for path in sorted(ROOT.glob(pat)):
            if _migrate_experiment_overlays(path):
                print(f"migrated experiment overlays {path.relative_to(ROOT)}")
                n += 1
    print(f"done — {n} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
