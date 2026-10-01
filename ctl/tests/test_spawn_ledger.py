#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest

from mas.ctl.executor.spawn_ledger import SpawnLedger


def test_spawn_ledger_enforces_session_wide_count_and_depth():
    ledger = SpawnLedger(max_depth=2, max_spawns=2)
    assert ledger.allow_spawn("s")
    ledger.enter("s")
    assert ledger.current_depth("s") == 1
    assert ledger.spawn_count("s") == 1
    assert ledger.allow_spawn("s")
    ledger.enter("s")
    assert not ledger.allow_spawn("s")
    ledger.exit("s")
    assert ledger.allow_spawn("s") is False  # spawn count remains at its cap
    ledger.exit("s")
    assert ledger.current_depth("s") == 0


def test_spawn_ledger_scopes_budgets_and_ids_by_parent_template():
    ledger = SpawnLedger(max_depth=1, max_spawns=1)
    first_id = ledger.mint_agent_id("root", "worker")
    second_id = ledger.mint_agent_id("root", "worker")

    assert first_id == "root.worker.1"
    assert second_id == "root.worker.2"
    ledger.enter("session-a")
    assert not ledger.allow_spawn("session-a")
    assert ledger.allow_spawn("session-b")


def test_spawn_ledger_rejects_invalid_bounds_and_underflow():
    with pytest.raises(ValueError, match="max_depth"):
        SpawnLedger(max_depth=0)
    ledger = SpawnLedger()
    with pytest.raises(RuntimeError, match="underflow"):
        ledger.exit("never-entered")


def test_spawn_ledger_checks_child_depth_type_and_boundary_values():
    ledger = SpawnLedger(max_depth=3)

    assert ledger.allows_child_depth(0)
    assert ledger.allows_child_depth(2)
    assert not ledger.allows_child_depth(3)
    assert not ledger.allows_child_depth("2")
    assert not ledger.allows_child_depth(2.9)
    assert not ledger.allows_child_depth(-1)
    assert not ledger.allows_child_depth(True)