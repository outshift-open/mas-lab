#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Budget tracker integration."""

from mas.runtime.boundary.gov.budget import BudgetTracker, budget_from_manifest


def test_budget_tracker_enforces_ceilings():
    tracker = BudgetTracker(max_tool_calls=1, max_llm_calls=1)
    assert tracker.allow_tool()
    tracker.note_tool()
    assert not tracker.allow_tool()


def test_budget_from_manifest_no_hidden_defaults_when_tools_present():
    manifest = {"spec": {"tools": [{"module_path": "x"}], "budget": {}}}
    tracker = budget_from_manifest(manifest)
    assert tracker.max_tool_calls is None
    assert tracker.max_llm_calls is None


def test_budget_from_manifest_honors_explicit_limits():
    manifest = {"spec": {"budget": {"max_tool_calls": 3, "max_llm_calls": 5}}}
    tracker = budget_from_manifest(manifest)
    assert tracker.max_tool_calls == 3
    assert tracker.max_llm_calls == 5
