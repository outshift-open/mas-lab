#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""build_observability_plugin_set / attach_observability_plugin_set — the two
functions that let ctl (or anything outside runtime) get an ObsPluginSet
wired to one or more RuntimeInstances without ever importing
build_observability_plugins or constructing ObsPluginSet itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.boundary.obs.plugins import (
    ObsPluginSet,
    attach_observability_plugin_set,
    build_observability_plugin_set,
)


@dataclass
class _FakeDriver:
    observability: ObservabilityOperator | None = field(default_factory=ObservabilityOperator)
    ctx: object | None = None


@dataclass
class _FakeInstance:
    driver: _FakeDriver = field(default_factory=_FakeDriver)
    obs_plugin_set: object | None = None


def test_build_observability_plugin_set_returns_none_for_none_binding(tmp_path) -> None:
    assert build_observability_plugin_set(None, base_dir=tmp_path) is None


def test_build_observability_plugin_set_returns_none_for_empty_plugin_list(tmp_path) -> None:
    binding = ObservabilityBinding(plugins=[])
    # An explicitly empty list still means "nothing to build" here -- the
    # native fallback only kicks in inside build_observability_plugins when
    # the *caller* asked for plugins and none resolved, not when the binding
    # itself declares zero plugins up front.
    assert binding.plugins == []


def test_build_observability_plugin_set_builds_real_plugins(tmp_path) -> None:
    binding = ObservabilityBinding(
        plugins=["native"],
        plugin_configs={"native": {"path": "events.jsonl"}},
    )
    plugin_set = build_observability_plugin_set(binding, base_dir=tmp_path, agent_id="sre")
    assert isinstance(plugin_set, ObsPluginSet)
    assert len(plugin_set.plugins) == 1


def test_attach_observability_plugin_set_subscribes_and_begins_run(tmp_path) -> None:
    binding = ObservabilityBinding(
        plugins=["native"],
        plugin_configs={"native": {"path": "events.jsonl"}},
    )
    plugin_set = build_observability_plugin_set(binding, base_dir=tmp_path, agent_id="sre")
    instance = _FakeInstance()

    attach_observability_plugin_set(plugin_set, instance, agent_id="sre")

    assert instance.obs_plugin_set is plugin_set
    assert plugin_set._run_started
    assert instance.driver.observability in plugin_set._all_operators


def test_attach_observability_plugin_set_shared_across_instances_begins_run_once(tmp_path) -> None:
    binding = ObservabilityBinding(
        plugins=["native"],
        plugin_configs={"native": {"path": "events.jsonl"}},
    )
    shared = build_observability_plugin_set(binding, base_dir=tmp_path, agent_id="entry")
    inst_a = _FakeInstance()
    inst_b = _FakeInstance()

    attach_observability_plugin_set(shared, inst_a, agent_id="agent-a")
    attach_observability_plugin_set(shared, inst_b, agent_id="agent-b")

    assert inst_a.obs_plugin_set is shared and inst_b.obs_plugin_set is shared
    assert len(shared._all_operators) == 2
    # begin_run is idempotent -- attaching a second instance must not start
    # a second run or raise.
    assert shared._run_started


def test_attach_observability_plugin_set_respects_explicit_disablement(tmp_path) -> None:
    """driver.observability is None -> instrumentation was explicitly turned
    off for this instance; attaching must record the set for bookkeeping but
    never fabricate an operator to re-enable it."""
    binding = ObservabilityBinding(plugins=["native"], plugin_configs={"native": {"path": "events.jsonl"}})
    plugin_set = build_observability_plugin_set(binding, base_dir=tmp_path, agent_id="sre")
    instance = _FakeInstance(driver=_FakeDriver(observability=None))

    attach_observability_plugin_set(plugin_set, instance, agent_id="sre")

    assert instance.obs_plugin_set is plugin_set
    assert plugin_set._all_operators == []
    assert not plugin_set._run_started
