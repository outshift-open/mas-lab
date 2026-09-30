#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""library-standard examples: categorized Agent/MAS scenarios."""

from __future__ import annotations

from pathlib import Path

import yaml

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
INDEX = EXAMPLES / "README.md"
_CATEGORIES = {
    "governance",
    "observability",
    "design-pattern",
    "memory",
    "workflow",
    "tools",
    "context",
}


def _scenarios() -> list[tuple[str, Path, str]]:
    """Return (category, dir, kind) for every example with agent.yaml or mas.yaml."""
    out: list[tuple[str, Path, str]] = []
    if not EXAMPLES.is_dir():
        return out
    for cat in sorted(p for p in EXAMPLES.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for scenario in sorted(p for p in cat.iterdir() if p.is_dir() and not p.name.startswith(".")):
            kind = None
            if (scenario / "mas.yaml").is_file():
                kind = "MAS"
            elif (scenario / "agent.yaml").is_file():
                kind = "Agent"
            if kind:
                out.append((cat.name, scenario, kind))
    return out


def test_example_categories_are_plugin_kinds() -> None:
    for cat, scenario, _ in _scenarios():
        assert cat in _CATEGORIES, f"{scenario}: category {cat!r} is not a plugin kind"


def test_index_lists_every_example() -> None:
    readme = INDEX.read_text(encoding="utf-8")
    scenarios = _scenarios()
    assert scenarios, "expected at least one example"
    for cat, scenario, kind in scenarios:
        rel = f"{cat}/{scenario.name}"
        assert rel in readme, f"{rel} missing from examples/README.md"
        assert kind in readme, f"{rel} kind {kind} missing from examples/README.md"
        cat_index = EXAMPLES / cat / "README.md"
        assert cat_index.is_file(), f"{cat}/README.md missing"
        assert scenario.name in cat_index.read_text(encoding="utf-8")


def test_examples_are_mas_v1_agent_or_mas() -> None:
    for cat, scenario, kind in _scenarios():
        name = "mas.yaml" if kind == "MAS" else "agent.yaml"
        doc = yaml.safe_load((scenario / name).read_text(encoding="utf-8"))
        assert doc["apiVersion"] == "mas/v1"
        assert doc["kind"] == kind
        assert scenario.parent.name == cat
