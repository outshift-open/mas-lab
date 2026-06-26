#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Execution plan construction and cartesian guards."""

from typing import Any


def build_execution_plan(
    scenario_ids: list,
    dataset_items: list,
    n_runs: int,
    *,
    execution: dict | None = None,
    strategy: str = "coverage",
) -> list[tuple[str, dict, int]]:
    """Return ordered ``(scenario_id, item, run_idx)`` triples."""
    execution = execution or {}
    design = execution.get("design") or {}
    mode = design.get("mode", "cartesian")

    if mode == "coupled":
        plan = _build_coupled_plan(design.get("couplings") or [], dataset_items, n_runs)
    elif mode == "one_factor":
        plan = _build_one_factor_plan(
            design,
            scenario_ids,
            dataset_items,
            n_runs,
        )
    else:
        plan = _build_cartesian_plan(scenario_ids, dataset_items, n_runs, strategy)

    enforce_max_executions(len(plan), execution)
    return plan


def _build_cartesian_plan(
    scenario_ids: list,
    dataset_items: list,
    n_runs: int,
    strategy: str,
) -> list[tuple[str, dict, int]]:
    if strategy == "depth":
        return [
            (scenario_id, item, run_idx)
            for scenario_id in scenario_ids
            for item in dataset_items
            for run_idx in range(n_runs)
        ]
    return [
        (scenario_id, item, run_idx)
        for run_idx in range(n_runs)
        for scenario_id in scenario_ids
        for item in dataset_items
    ]


def _build_coupled_plan(
    couplings: list[dict],
    dataset_items: list,
    n_runs: int,
) -> list[tuple[str, dict, int]]:
    items_by_id = {str(i.get("id")): i for i in dataset_items}
    plan: list[tuple[str, dict, int]] = []
    for pair in couplings:
        scenario_id = pair["scenario"]
        item_ids = pair.get("items")
        if item_ids is None:
            selected = dataset_items
        else:
            selected = [items_by_id[str(iid)] for iid in item_ids]
        for run_idx in range(n_runs):
            for item in selected:
                plan.append((scenario_id, item, run_idx))
    return plan


def _build_one_factor_plan(
    design: dict,
    scenario_ids: list,
    dataset_items: list,
    n_runs: int,
) -> list[tuple[str, dict, int]]:
    """Vary one axis declared in design.vary; pin others via couplings or full grid subset."""
    vary = design.get("vary") or {}
    axis = vary.get("axis")
    values = vary.get("values") or []
    if not axis or not values:
        return _build_cartesian_plan(scenario_ids, dataset_items, n_runs, "coverage")

    pinned_scenarios = set(design.get("pin_scenarios") or scenario_ids)
    pinned_items = design.get("pin_items")
    base_items = (
        [i for i in dataset_items if str(i.get("id")) in {str(x) for x in pinned_items}]
        if pinned_items
        else dataset_items
    )

    plan: list[tuple[str, dict, int]] = []
    if axis == "scenario":
        for scenario_id in values:
            if scenario_id not in pinned_scenarios and pinned_scenarios:
                continue
            for run_idx in range(n_runs):
                for item in base_items:
                    plan.append((scenario_id, item, run_idx))
    elif axis == "item":
        items_by_id = {str(i.get("id")): i for i in dataset_items}
        for item_id in values:
            item = items_by_id.get(str(item_id))
            if item is None:
                continue
            for scenario_id in pinned_scenarios:
                for run_idx in range(n_runs):
                    plan.append((scenario_id, item, run_idx))
    else:
        plan = _build_cartesian_plan(scenario_ids, dataset_items, n_runs, "coverage")
    return plan


def enforce_max_executions(plan_len: int, execution: dict | None) -> None:
    if not execution:
        return
    design = execution.get("design")
    if not isinstance(design, dict):
        return
    max_executions = design.get("max_executions")
    if max_executions is None:
        return
    limit = int(max_executions)
    if plan_len > limit:
        raise RuntimeError(
            f"Execution grid {plan_len} exceeds "
            f"execution.design.max_executions={limit}. "
            "Reduce scenarios/items/n_runs or raise the limit."
        )
