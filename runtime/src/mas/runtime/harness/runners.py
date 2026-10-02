#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runners: layer-2 compositions as call sequences over ControlContract.

These functions are the finished DAG product. They do not implement pause,
snapshot, or spawn. They call the same SessionControl / Session methods
every other surface uses.
"""

from __future__ import annotations

from typing import Any, Callable

from mas.runtime.harness.catalog import HarnessCatalog, default_catalog


def run_detective(
    control: Any,
    session_id: str,
    *,
    reason: str = "detective",
    inspect: bool = True,
) -> dict[str, Any]:
    """pause → list tree → optional investigate branch. Leaves: detective.uses."""
    control.pause(session_id, reason=reason)
    nodes = control.list_checkpoints(session_id)
    child = None
    if inspect and hasattr(control, "fork_investigation"):
        child = control.fork_investigation(session_id)
    return {"nodes": nodes, "investigation": child, "harness": "detective"}


def run_whatif(
    session: Any,
    *,
    variants: list[str | None],
    run_turn: Callable[[str | None], Any],
) -> list[Any]:
    """N branches from the live snapshot; none promoted unless a variant says so."""
    results = []
    for steering in variants:
        with session.branch(steering=steering) as handle:
            run_turn(steering)
            results.append(handle.inspect())
    return results


def run_evolution(
    session: Any,
    *,
    mutations: list[Callable[[Any], None]],
    score: Callable[[Any], float],
    persist_store: Any | None = None,
) -> Any:
    """Branch × spec_delta × score; keep the winner (promote / persist)."""
    origin = session.take_snapshot(label="evolution-origin")
    winner = None
    best_score = float("-inf")
    for mutate in mutations:
        session.restore_snapshot(origin)
        with session.branch() as handle:
            mutate(session)
            snap = handle.inspect()
            value = score(snap)
            if value > best_score:
                best_score = value
                winner = snap
                if persist_store is not None:
                    handle.persist(persist_store)
                handle.promote()
    if winner is None:
        session.restore_snapshot(origin)
    return winner


def catalog_for_runner(catalog: HarnessCatalog | None = None) -> HarnessCatalog:
    return catalog if catalog is not None else default_catalog()
