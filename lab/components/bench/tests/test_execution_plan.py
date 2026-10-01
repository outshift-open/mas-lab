#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Coupled execution plan keys off dataset item id only."""
from __future__ import annotations

from mas.lab.benchmark.execution.plan import _build_coupled_plan


def test_coupled_plan_is_id_pairs_not_cartesian():
    ids = [f"item-{i}" for i in range(25)]
    items = [{"id": i, "inputs": {"user": i}} for i in ids]
    couplings = [{"scenario": i, "items": [i]} for i in ids]
    plan = _build_coupled_plan(couplings, items, n_runs=1)
    assert len(plan) == 25
    assert [(s, i["id"]) for s, i, _ in plan] == list(zip(ids, ids))


def test_coupled_plan_pairs_scenario_to_item_id():
    items = [
        {"id": "celestia-weekend", "inputs": {"user": "A"}},
        {"id": "verdantia-budget", "inputs": {"user": "B"}},
    ]
    couplings = [
        {"scenario": "celestia-weekend", "items": ["celestia-weekend"]},
        {"scenario": "verdantia-budget", "items": ["verdantia-budget"]},
    ]
    plan = _build_coupled_plan(couplings, items, n_runs=1)
    assert [(s, i["id"]) for s, i, _ in plan] == [
        ("celestia-weekend", "celestia-weekend"),
        ("verdantia-budget", "verdantia-budget"),
    ]
