#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""spec/gov.py — governance plugin-list parsing and KernelConfig wiring."""

from __future__ import annotations

import pytest

from mas.runtime.spec.gov import SpecBindingError, build_kernel_config, parse_gov_spec


class _CustomGovernancePlugin:
    """Module-level (not nested in a test) so the registry's load_class() —
    importlib.import_module(self.module) then getattr — can actually find it."""

    def __init__(self, **cfg: object) -> None:
        self.cfg = cfg

    def evaluate_egress(self, intent, *, config):
        from mas.runtime.kernel.coupling import GovDecision

        return GovDecision.ALLOW, "custom", ""


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


def test_unknown_plugin_name_is_skipped_not_crashed() -> None:
    """No plugin class is ever named/imported directly in build_kernel_config
    — an unresolvable name just logs a warning and leaves egress_governance_plugin
    unset, the same as an empty governance list."""
    binding = parse_gov_spec(["totally_unknown_plugin_name"])
    config = build_kernel_config(binding)
    assert config.egress_governance_plugin is None


def test_named_plugin_resolves_via_registry_not_a_hardcoded_check() -> None:
    """Regression: build_kernel_config used to hardcode
    `if name in {"sample_governance", "sample_governance@v1"}`. A plugin
    registered under an arbitrary urn/shortcut — not sample_governance, not
    anything build_kernel_config's source mentions by name — must resolve
    and construct correctly purely through the plugin registry.

    register_plugin mutates get_registry()'s process-wide singleton with no
    built-in unregister — clean up the entry/alias this test adds so it
    doesn't leak into any other test that happens to run in this same
    process (e.g. one that enumerates all registered governance plugins).
    """
    from mas.runtime.registry import get_registry, register_plugin

    urn = "mas.gov.test_gov_spec_custom_plugin"
    shortcut = "test_gov_spec_custom_governance"
    try:
        register_plugin(
            urn,
            _CustomGovernancePlugin,
            shortcuts=[shortcut],
            attributes={"plugin_type": "governance"},
        )

        binding = parse_gov_spec([{shortcut: {"threshold": 3}}])
        config = build_kernel_config(binding)

        assert isinstance(config.egress_governance_plugin, _CustomGovernancePlugin)
        assert config.egress_governance_plugin.cfg == {"threshold": 3}
    finally:
        reg = get_registry()
        reg._entries.pop(urn, None)
        reg._aliases.pop(shortcut, None)


def test_flags_only_fallback_also_resolves_sample_governance_via_registry() -> None:
    """The hitl_on_tool-without-a-named-plugin fallback used to call
    SampleGovernancePlugin(**cfg) directly (a hardcoded import). It must now
    go through the exact same registry lookup as the named-plugin path."""
    import dataclasses

    binding = dataclasses.replace(parse_gov_spec([]), hitl_on_tool=True)
    config = build_kernel_config(binding)
    assert config.egress_governance_plugin is not None
    assert config.egress_governance_plugin.config.hitl_on_tool is True


def test_agent_spec_threads_through_to_kernel_config() -> None:
    spec = {"tools": ["lookup_schedule"], "models": [{"model": "gpt-4o"}]}
    binding = parse_gov_spec(None)
    config = build_kernel_config(binding, agent_spec=spec)
    assert config.agent_spec == spec


def test_agent_spec_defaults_to_none() -> None:
    config = build_kernel_config(parse_gov_spec(None))
    assert config.agent_spec is None
