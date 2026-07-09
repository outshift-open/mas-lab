#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Coverage for ctl.session.observability setup glue after the switch to
runtime's build/attach_observability_plugin_set delegation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mas.ctl.adapters.obs.config import ObservabilityConfig
from mas.ctl.session.observability import (
    obs_config_to_binding,
    setup_instance_obs,
    setup_observability,
    setup_observability_from_binding,
    setup_shared_obs,
)
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.operator import ObservabilityOperator


@dataclass
class _FakeDriver:
    observability: ObservabilityOperator = field(default_factory=ObservabilityOperator)
    ctx: object | None = None


@dataclass
class _FakeInstance:
    driver: _FakeDriver = field(default_factory=_FakeDriver)
    obs_plugin_set: object | None = None


def test_obs_config_to_binding_disabled_returns_none() -> None:
    assert obs_config_to_binding(ObservabilityConfig(enabled=False)) is None


def test_obs_config_to_binding_defaults_native_and_events_path(tmp_path: Path) -> None:
    cfg = ObservabilityConfig(enabled=True, events_file=str(tmp_path / "e.jsonl"))
    binding = obs_config_to_binding(cfg)
    assert binding is not None
    assert binding.plugins == ["native"]
    assert binding.plugin_configs["native"]["path"] == str(tmp_path / "e.jsonl")


def test_setup_instance_obs_builds_and_attaches(tmp_path: Path) -> None:
    inst = _FakeInstance()
    cfg = ObservabilityConfig(enabled=True, plugins=["native"], agent_id="planner")
    plugin_set = setup_instance_obs(inst, cfg, base_dir=tmp_path)
    assert plugin_set is not None
    assert inst.obs_plugin_set is plugin_set
    plugin_set.close()


def test_setup_instance_obs_disabled_returns_none(tmp_path: Path) -> None:
    assert setup_instance_obs(_FakeInstance(), ObservabilityConfig(enabled=False), base_dir=tmp_path) is None


def test_setup_shared_obs_attaches_all_and_begins_run(tmp_path: Path) -> None:
    a, b = _FakeInstance(), _FakeInstance()
    cfg = ObservabilityConfig(enabled=True, plugins=["native"], agent_id="a")
    shared = setup_shared_obs({"a": a, "b": b}, cfg, base_dir=tmp_path, entry_agent_id="a")
    assert shared is not None
    assert a.obs_plugin_set is shared and b.obs_plugin_set is shared
    shared.close()


def test_setup_shared_obs_disabled_returns_none(tmp_path: Path) -> None:
    assert setup_shared_obs({}, ObservabilityConfig(enabled=False), base_dir=tmp_path, entry_agent_id="a") is None


def test_setup_observability_legacy_returns_recorder(tmp_path: Path) -> None:
    inst = _FakeInstance()
    cfg = ObservabilityConfig(enabled=True, plugins=["native"], agent_id="planner")
    rec = setup_observability(inst, cfg, base_dir=tmp_path)
    assert rec is not None
    rec.plugin_set.close()


def test_setup_observability_from_binding_reuses_existing_set(tmp_path: Path) -> None:
    inst = _FakeInstance()
    binding = ObservabilityBinding(plugins=["native"])
    rec = setup_observability_from_binding(inst, binding, base_dir=tmp_path, agent_id="planner")
    assert rec is not None
    assert inst.obs_plugin_set is rec.plugin_set
    rec.plugin_set.close()


def test_setup_observability_from_binding_empty_plugins_returns_none(tmp_path: Path) -> None:
    rec = setup_observability_from_binding(
        _FakeInstance(), ObservabilityBinding(plugins=[]), base_dir=tmp_path
    )
    assert rec is None
