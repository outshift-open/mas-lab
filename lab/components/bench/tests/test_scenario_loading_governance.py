#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Overlay governance-list injection — _apply_overlay_governance coverage.

Regression suite: the same block used to be duplicated verbatim in both
load_scenario_config and load_stacked_config, with two bugs neither had a
test for — a same-key overwrite (two overlays both using "sample_governance"
silently dropped the first one's policies once the declarative policy engine
was actually wired up) and a falsy-empty-list check (an explicit
``governance: []`` meant to clear a previous overlay's contribution was
silently ignored, since ``if [] and ...`` never runs).
"""

from __future__ import annotations

from mas.lab.lab.config.scenario_loading import _apply_overlay_governance


def _config(governance: list | None = None) -> dict:
    return {"agents": [{"id": "a1", "governance": governance or []}]}


def test_absent_key_is_a_no_op() -> None:
    config = _config(governance=[{"x": 1}])
    applied = _apply_overlay_governance(None, {}, config)
    assert applied is False
    assert config["agents"][0]["governance"] == [{"x": 1}]


def test_non_empty_governance_concatenates() -> None:
    config = _config(governance=[{"x": 1}])
    applied = _apply_overlay_governance(None, {"governance": [{"y": 2}]}, config)
    assert applied is True
    assert config["agents"][0]["governance"] == [{"x": 1}, {"y": 2}]


def test_explicit_empty_list_clears_regression() -> None:
    """Regression: an explicit governance: [] used to be falsy and skip the
    whole injection block, leaving a previous overlay's governance untouched
    instead of clearing it as the overlay author intended."""
    config = _config(governance=[{"sample_governance": {"policies": [{"name": "old"}]}}])
    applied = _apply_overlay_governance(None, {"governance": []}, config)
    assert applied is True
    assert config["agents"][0]["governance"] == []


def test_overlay_spec_takes_precedence_when_overlay_dict_present() -> None:
    config = _config()
    overlay = {"spec": {"governance": [{"a": 1}]}}
    _apply_overlay_governance(overlay, {"governance": [{"b": 2}]}, config)
    assert config["agents"][0]["governance"] == [{"a": 1}]


def test_falls_back_to_overlay_spec_when_overlay_has_no_governance_key() -> None:
    config = _config()
    overlay = {"spec": {}}
    _apply_overlay_governance(overlay, {"governance": [{"b": 2}]}, config)
    assert config["agents"][0]["governance"] == [{"b": 2}]


def test_no_agents_is_a_no_op() -> None:
    config: dict = {}
    applied = _apply_overlay_governance(None, {"governance": [{"a": 1}]}, config)
    assert applied is False
