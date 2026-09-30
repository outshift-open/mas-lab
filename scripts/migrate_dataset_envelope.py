#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""One-shot migration: flat dataset items → inputs/expectations envelope."""
from __future__ import annotations

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


def _flatten_role_list(value):
    """[{role, content}, ...] → string or list of strings. Extra HITL as a list."""
    if isinstance(value, str):
        return value, []
    if not isinstance(value, list) or not value:
        return value, []
    if all(isinstance(m, str) for m in value):
        return (value[0] if len(value) == 1 else value), []
    if not all(isinstance(m, dict) and "content" in m for m in value):
        return value, []
    users: list[str] = []
    hitls: list[str] = []
    for message in value:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        if role == "hitl":
            hitls.append(content)
        else:
            users.append(content)
    if not users:
        return value, hitls
    return (users[0] if len(users) == 1 else users), hitls


def _migrate_item(item: dict) -> dict:
    if "inputs" in item:
        if any(k in item for k in LEGACY_ITEM_KEYS):
            raise ValueError(f"item {item.get('id')!r} mixes envelope and legacy fields")
        inputs = dict(item["inputs"])
        flattened, extra_hitl = _flatten_role_list(inputs.get("user"))
        if flattened is not inputs.get("user"):
            inputs["user"] = flattened
        if extra_hitl:
            existing = inputs.get("hitl")
            if existing is None:
                inputs["hitl"] = extra_hitl
            elif isinstance(existing, str):
                inputs["hitl"] = [existing, *extra_hitl]
            elif isinstance(existing, list):
                inputs["hitl"] = list(existing) + extra_hitl
        if inputs != item["inputs"]:
            return {**item, "inputs": inputs}
        return item

    if "prompt" not in item:
        raise ValueError(f"item {item.get('id')!r} has no prompt")
    inputs: dict = {"user": str(item["prompt"])}
    hitl: list[str] = []
    extra_users: list[str] = []
    for turn in item.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "user")
        content = str(turn.get("content") or "")
        if role == "hitl":
            hitl.append(content)
        elif role == "user" and content:
            extra_users.append(content)
    if extra_users:
        inputs["user"] = [str(item["prompt"]), *extra_users]
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


COPYRIGHT_HEADER = (
    "#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates\n"
    "#  SPDX-License-Identifier: Apache-2.0\n"
)


def _leading_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(True):
        if line.startswith("#") or not line.strip():
            lines.append(line)
        else:
            break
    return "".join(lines)


def _dump_yaml(path: Path, data: dict, original_text: str) -> None:
    body = yaml.dump(
        data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120
    )
    header = _leading_comments(original_text)
    if "SPDX-License-Identifier" not in header:
        header = COPYRIGHT_HEADER + ("\n" if header else "\n")
    elif header and not header.endswith("\n"):
        header += "\n"
    path.write_text(header + body, encoding="utf-8")


def _migrate_yaml(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    data = yaml.safe_load(original)
    if not isinstance(data, dict):
        return False
    changed = False
    if data.get("kind") == "Dataset" and isinstance(data.get("spec"), dict):
        items = data["spec"].get("items")
        if isinstance(items, list) and items:
            new_items = _migrate_items(items)
            if new_items != items:
                data["spec"]["items"] = new_items
                changed = True
    elif isinstance(data.get("items"), list):
        new_items = _migrate_items(data["items"])
        if new_items != data["items"]:
            data["items"] = new_items
            changed = True
    if changed:
        _dump_yaml(path, data, original)
    return changed


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
        "labs/**/datasets/**/*.yaml",
        "docs/tutorials/**/dataset*.yaml",
        "lab/components/controller/tests/fixtures/**/datasets/**/*.yaml",
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
    for pat in exp_patterns:
        for path in sorted(ROOT.glob(pat)):
            if _migrate_experiment_overlays(path):
                print(f"migrated experiment overlays {path.relative_to(ROOT)}")
                n += 1
    print(f"done — {n} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
