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
        {"id": "routing-policy-rollback", "inputs": {"user": "A"}},
        {"id": "profile-api-restart", "inputs": {"user": "B"}},
    ]
    couplings = [
        {"scenario": "routing-policy-rollback", "items": ["routing-policy-rollback"]},
        {"scenario": "profile-api-restart", "items": ["profile-api-restart"]},
    ]
    plan = _build_coupled_plan(couplings, items, n_runs=1)
    assert [(s, i["id"]) for s, i, _ in plan] == [
        ("routing-policy-rollback", "routing-policy-rollback"),
        ("profile-api-restart", "profile-api-restart"),
    ]
