#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Wire observability from manifest config -> runtime instance."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from mas.ctl.adapters.obs.config import ObservabilityConfig
from mas.ctl.adapters.obs.session import SessionObservabilityRecorder
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.loader import ObsPluginSet, load_obs_plugins

if TYPE_CHECKING:
    from mas.runtime.driver.instance import RuntimeInstance


def obs_config_to_binding(config: ObservabilityConfig) -> ObservabilityBinding | None:
    """Convert ctl ObservabilityConfig -> runtime ObservabilityBinding."""
    if not config.enabled:
        return None
    plugins = list(config.plugins) if config.plugins else ["native"]
    plugin_configs = dict(config.plugin_configs or {})
    if config.events_file:
        native_cfg = dict(plugin_configs.get("native") or {})
        native_cfg.setdefault("path", config.events_file)
        plugin_configs["native"] = native_cfg
    return ObservabilityBinding(
        plugins=plugins,
        plugin_configs=plugin_configs,
        events_file=config.events_file,
        stdout=config.events_stdout,
    )


def setup_instance_obs(
    instance: "RuntimeInstance",
    config: ObservabilityConfig,
    *,
    base_dir: Path,
    agent_id: str | None = None,
) -> ObsPluginSet | None:
    """Build plugins, subscribe to instance's operator, and begin run. Returns plugin_set."""
    binding = obs_config_to_binding(config)
    if binding is None:
        return None
    effective_agent_id = agent_id or config.agent_id or "agent"
    plugins = load_obs_plugins(binding, base_dir=base_dir, agent_id=effective_agent_id)
    plugin_set = ObsPluginSet(plugins=plugins)
    op = instance.driver.observability
    if op is not None:
        plugin_set.subscribe_to(op, agent_id=effective_agent_id)
        plugin_set.begin_run(op)
    instance.obs_plugin_set = plugin_set
    return plugin_set


def setup_shared_obs(
    instances: "dict[str, RuntimeInstance]",
    config: ObservabilityConfig,
    *,
    base_dir: Path,
    entry_agent_id: str,
) -> ObsPluginSet | None:
    """One plugin set shared across all agents in a multi-agent run."""
    binding = obs_config_to_binding(config)
    if binding is None:
        return None
    shared_plugins = load_obs_plugins(binding, base_dir=base_dir, agent_id=entry_agent_id)
    shared_set = ObsPluginSet(plugins=shared_plugins)
    for agent_id, instance in instances.items():
        op = instance.driver.observability
        if op is not None:
            shared_set.subscribe_to(op, agent_id=agent_id)
        instance.obs_plugin_set = shared_set
    # begin_run on the entry agent's operator
    entry_instance = instances.get(entry_agent_id) or next(iter(instances.values()), None)
    if entry_instance is not None and entry_instance.driver.observability is not None:
        shared_set.begin_run(entry_instance.driver.observability)
    return shared_set


# ---------------------------------------------------------------------------
# Backward compatibility — legacy callers still used by runner.py and tests
# ---------------------------------------------------------------------------

ObsSetupFn = Callable[["RuntimeInstance", str], SessionObservabilityRecorder | None]


def setup_observability(
    instance: "RuntimeInstance",
    config: ObservabilityConfig,
    *,
    base_dir: Path,
) -> SessionObservabilityRecorder | None:
    """Legacy path: ObservabilityConfig → runtime loader → ObsPluginSet."""
    binding = obs_config_to_binding(config)
    if binding is None:
        return None
    plugins = load_obs_plugins(binding, base_dir=base_dir, agent_id=config.agent_id)
    plugin_set = ObsPluginSet(plugins=plugins)
    op = instance.driver.observability
    if op is not None:
        plugin_set.subscribe_to(op, agent_id=config.agent_id)
        plugin_set.begin_run(op)
    instance.obs_plugin_set = plugin_set
    return SessionObservabilityRecorder(plugin_set=plugin_set)


def create_shared_observability(
    config: ObservabilityConfig,
    *,
    base_dir: Path,
):
    """Shared plugin set for multi-agent MAS runs (shared events.jsonl).

    Returns (shared_set, setup_fn) where shared_set.close() ends the run.
    setup_fn(instance, agent_id) subscribes the instance and returns a recorder.
    """
    binding = obs_config_to_binding(config)
    if binding is None:
        return None, None

    entry_agent_id = config.agent_id or "agent"
    shared_plugins = load_obs_plugins(binding, base_dir=base_dir, agent_id=entry_agent_id)
    shared_set = ObsPluginSet(plugins=shared_plugins)
    _begun = {"done": False}

    def setup(instance: "RuntimeInstance", agent_id: str) -> SessionObservabilityRecorder:
        op = instance.driver.observability
        if op is not None:
            shared_set.subscribe_to(op, agent_id=agent_id)
            if not _begun["done"]:
                shared_set.begin_run(op)
                _begun["done"] = True
        instance.obs_plugin_set = shared_set
        return SessionObservabilityRecorder(plugin_set=shared_set, owns_plugin_set=False)

    return shared_set, setup


def _bind_plugin_set_to_instance(
    instance: "RuntimeInstance",
    plugin_set: ObsPluginSet,
    *,
    agent_id: str,
) -> SessionObservabilityRecorder:
    """Subscribe *plugin_set* to the instance's operator and return a recorder."""
    from mas.runtime.boundary.obs.operator import ObservabilityOperator

    driver = instance.driver
    op = driver.observability
    if op is None:
        # observability is explicitly disabled on this instance — don't re-enable it.
        instance.obs_plugin_set = plugin_set
        return SessionObservabilityRecorder(plugin_set=plugin_set)
    if not isinstance(op, ObservabilityOperator):
        op = ObservabilityOperator()
        driver.observability = op

    plugin_set.subscribe_to(op, agent_id=agent_id)
    plugin_set.begin_run(op)
    instance.obs_plugin_set = plugin_set

    return SessionObservabilityRecorder(plugin_set=plugin_set)


def setup_observability_from_binding(
    instance: "RuntimeInstance",
    binding: ObservabilityBinding,
    *,
    base_dir: Path,
    agent_id: str = "agent",
) -> SessionObservabilityRecorder | None:
    """New path: ObservabilityBinding → runtime loader → ObsPluginSet."""
    if not binding.plugins:
        return None

    plugin_set: ObsPluginSet | None = getattr(instance, "obs_plugin_set", None)
    if plugin_set is None:
        plugins = load_obs_plugins(binding, base_dir=base_dir, agent_id=agent_id)
        plugin_set = ObsPluginSet(plugins=plugins)
        instance.obs_plugin_set = plugin_set

    return _bind_plugin_set_to_instance(instance, plugin_set, agent_id=agent_id)


