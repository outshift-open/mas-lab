#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""spec/gov.py — governance plugin-list parsing and KernelConfig wiring."""

from __future__ import annotations

import pytest

from mas.runtime.spec.gov import SpecBindingError, build_kernel_config, parse_gov_spec


def test_same_plugin_key_merges_policies_instead_of_overwriting_regression() -> None:
    """Regression: two overlay entries both using "sample_governance" used to
    silently overwrite (configs[name] = dict(cfg)), dropping the first
    overlay's entire policy set once the declarative policy engine was
    actually wired into build_kernel_config — previously invisible because
    binding.policies was parsed and discarded."""
    binding = parse_gov_spec([
        {"sample_governance": {"policies": [{"name": "budget-cap", "trigger": {"on": "budget_threshold"}, "action": "block"}]}},
        {"sample_governance": {"policies": [{"name": "forbidden-destination", "trigger": {"on": "tool_input"}, "action": "block"}]}},
    ])
    names = {p["name"] for p in binding.policies}
    assert names == {"budget-cap", "forbidden-destination"}


def test_same_plugin_key_scalar_field_last_value_wins() -> None:
    binding = parse_gov_spec([
        {"sample_governance": {"hitl_on_tool": False}},
        {"sample_governance": {"hitl_on_tool": True}},
    ])
    assert binding.hitl_on_tool is True


def test_build_kernel_config_wires_merged_policies() -> None:
    binding = parse_gov_spec([
        {"sample_governance": {"policies": [{"name": "p1", "trigger": {"on": "tool_input", "tool": "*", "condition": "", "evaluation": "deterministic"}, "action": "log"}]}},
        {"sample_governance": {"policies": [{"name": "p2", "trigger": {"on": "tool_input", "tool": "*", "condition": "", "evaluation": "deterministic"}, "action": "log"}]}},
    ])
    config = build_kernel_config(binding)
    assert config.policy_engine is not None
    assert {p.name for p in config.policy_engine.policies} == {"p1", "p2"}


def test_malformed_policy_raises_spec_binding_error_regression() -> None:
    """Regression: a malformed declarative policy (unrecognized action) used
    to raise a raw ValueError from deep inside PolicyDefinition.__post_init__,
    instead of this module's own SpecBindingError every other malformed
    governance shape raises."""
    binding = parse_gov_spec([
        {"sample_governance": {"policies": [
            {"name": "bad-policy", "trigger": {"on": "tool_input"}, "action": "not_a_real_action"},
        ]}}
    ])
    with pytest.raises(SpecBindingError, match="bad-policy"):
        build_kernel_config(binding)


def test_malformed_policy_missing_trigger_key_raises_spec_binding_error() -> None:
    binding = parse_gov_spec([
        {"sample_governance": {"policies": [
            {"name": "no-trigger", "action": "block"},
        ]}}
    ])
    with pytest.raises(SpecBindingError, match="no-trigger"):
        build_kernel_config(binding)
