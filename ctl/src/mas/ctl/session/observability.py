#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Wire observability from manifest config -> runtime instance.

ctl is agnostic to plugins: everything here converts ctl-side config into an
``ObservabilityBinding`` (pure data, see ``mas.runtime.boundary.obs.binding``)
and asks runtime to build/attach the actual plugin instances via
``build_observability_plugin_set`` / ``attach_observability_plugin_set``.
This module only orchestrates *when* that happens (single instance, a
pre-built dict of instances, or instances discovered lazily one at a time)
and wraps the result in ctl's own ``SessionObservabilityRecorder`` lifecycle
handle — it never imports ``build_observability_plugins`` or constructs an
``ObsPluginSet`` itself, the same way it never resolves a ``design_pattern``
plugin directly (that happens inside runtime's own
``mas.runtime.boundary.context.dp_inject``).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mas.ctl.adapters.obs.config import ObservabilityConfig
from mas.ctl.adapters.obs.session import SessionObservabilityRecorder
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.plugins import (
    ObsPluginSet,
    attach_observability_plugin_set,
    build_observability_plugin_set,
)

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
    effective_agent_id = agent_id or config.agent_id or "agent"
    plugin_set = build_observability_plugin_set(binding, base_dir=base_dir, agent_id=effective_agent_id)
    if plugin_set is None:
        return None
    attach_observability_plugin_set(plugin_set, instance, agent_id=effective_agent_id)
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
    shared_set = build_observability_plugin_set(binding, base_dir=base_dir, agent_id=entry_agent_id)
    if shared_set is None:
        return None
    for agent_id, instance in instances.items():
        attach_observability_plugin_set(shared_set, instance, agent_id=agent_id, begin_run=False)
    # begin_run on the entry agent's operator
    entry_instance = instances.get(entry_agent_id) or next(iter(instances.values()), None)
    if entry_instance is not None and entry_instance.driver.observability is not None:
        shared_set.begin_run(entry_instance.driver.observability)
    return shared_set


# ---------------------------------------------------------------------------
# Backward compatibility — legacy callers still used by runner.py and tests
# ---------------------------------------------------------------------------


def setup_observability(
    instance: "RuntimeInstance",
    config: ObservabilityConfig,
    *,
    base_dir: Path,
) -> SessionObservabilityRecorder | None:
    """Legacy path: ObservabilityConfig → runtime plugins → ObsPluginSet."""
    binding = obs_config_to_binding(config)
    plugin_set = build_observability_plugin_set(binding, base_dir=base_dir, agent_id=config.agent_id)
    if plugin_set is None:
        return None
    attach_observability_plugin_set(plugin_set, instance, agent_id=config.agent_id or "agent")
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
    entry_agent_id = config.agent_id or "agent"
    shared_set = build_observability_plugin_set(binding, base_dir=base_dir, agent_id=entry_agent_id)
    if shared_set is None:
        return None, None

    def setup(instance: "RuntimeInstance", agent_id: str) -> SessionObservabilityRecorder:
        # begin_run is idempotent (see ObsPluginSet.begin_run) -- passing
        # begin_run=True here is safe even though several instances share
        # this same plugin_set; only the first attach actually starts the run.
        attach_observability_plugin_set(shared_set, instance, agent_id=agent_id)
        return SessionObservabilityRecorder(plugin_set=shared_set, owns_plugin_set=False)

    return shared_set, setup


def setup_observability_from_binding(
    instance: "RuntimeInstance",
    binding: ObservabilityBinding,
    *,
    base_dir: Path,
    agent_id: str = "agent",
) -> SessionObservabilityRecorder | None:
    """New path: ObservabilityBinding → runtime plugins → ObsPluginSet."""
    if binding is None or not binding.plugins:
        return None

    plugin_set: ObsPluginSet | None = getattr(instance, "obs_plugin_set", None)
    if plugin_set is None:
        plugin_set = build_observability_plugin_set(binding, base_dir=base_dir, agent_id=agent_id)
        if plugin_set is None:
            return None

    attach_observability_plugin_set(plugin_set, instance, agent_id=agent_id)
    return SessionObservabilityRecorder(plugin_set=plugin_set)
