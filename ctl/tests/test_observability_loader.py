#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for manifest-driven observability plugin loading."""

from __future__ import annotations

from mas.ctl.adapters.obs.config import ObservabilityConfig
from mas.ctl.session.observability import obs_config_to_binding
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.plugins import ObsPluginSet, build_observability_plugins


def test_load_obs_config_to_binding_and_plugins(tmp_path) -> None:
    config = ObservabilityConfig(
        enabled=True,
        plugins=["native"],
        plugin_configs={"native": {"path": "traces/events.jsonl"}},
        agent_id="sre",
    )
    binding = obs_config_to_binding(config)
    assert binding is not None
    plugins = build_observability_plugins(binding, base_dir=tmp_path, agent_id=config.agent_id)
    plugin_set = ObsPluginSet(plugins=plugins)
    assert plugin_set is not None
    assert len(plugin_set.plugins) == 1


def test_load_obs_plugins_native(tmp_path) -> None:
    """Runtime loader builds a NativeObservabilityPlugin from ObservabilityBinding."""
    from mas.library.standard.plugins.observability.native_plugin import NativeObservabilityPlugin

    binding = ObservabilityBinding(
        plugins=["native"],
        plugin_configs={"native": {"path": "traces/events.jsonl"}},
    )
    plugins = build_observability_plugins(binding, base_dir=tmp_path, agent_id="sre")
    assert len(plugins) == 1
    assert isinstance(plugins[0], NativeObservabilityPlugin)


def test_load_obs_plugins_defaults_to_native_when_no_plugins(tmp_path) -> None:
    """Empty plugin list defaults to native."""
    from mas.library.standard.plugins.observability.native_plugin import NativeObservabilityPlugin

    binding = ObservabilityBinding(plugins=[])
    plugins = build_observability_plugins(binding, base_dir=tmp_path)
    assert len(plugins) == 1
    assert isinstance(plugins[0], NativeObservabilityPlugin)
