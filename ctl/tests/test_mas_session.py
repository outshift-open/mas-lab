#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mas.ctl.compose.models import AgentBindSlice, EffectiveBindManifest
from mas.ctl.compose.models import PlacementPlan
from mas.ctl.compose.runner import ComposeResult
from mas.ctl.executor.mas_session import (
    agent_manifest_label,
    entry_agent_id,
    is_sequential_workflow,
    prepare_delegation_entry_session,
    resolve_entry_pattern_plugin_id,
    sequential_workflow_payload,
)
from mas.ctl.benchmark.runner_dispatch import is_mas_manifest_kind, mas_manifest_path


def test_entry_agent_id_from_workflow_entry():
    mas = {"spec": {"workflow": {"entry": "moderator"}}}
    assert entry_agent_id(mas) == "moderator"


def test_agent_manifest_label_from_loaded_runtime_dict(tmp_path: Path):
    agent_path = tmp_path / "agent.yaml"
    agent_path.write_text("kind: agent\nmetadata:\n  name: qa-agent\n", encoding="utf-8")
    runtime_cfg = {
        "_loaded_mas_raw": True,
        "mas": {"entry_agent": "qa-agent"},
        "agents": [{"id": "qa-agent", "name": "qa-agent"}],
    }
    assert agent_manifest_label(runtime_cfg, agent_path) == "qa-agent"
    assert agent_manifest_label(runtime_cfg, tmp_path / "agent.yaml") != "agent"


def test_agent_manifest_label_prefers_metadata_over_stem(tmp_path: Path):
    agent_path = tmp_path / "agent.yaml"
    doc = {"metadata": {"name": "qa-agent"}, "spec": {}}
    assert agent_manifest_label(doc, agent_path) == "qa-agent"


def test_resolve_entry_pattern_plugin_id_from_bind():
    compose = ComposeResult(
        mas_id="test",
        mas_config={},
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="test",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[AgentBindSlice(agent_id="alpha", pattern_plugin_id="cot@v1")],
        ),
        plan=PlacementPlan(),
    )
    assert resolve_entry_pattern_plugin_id(compose, "alpha") == "cot@v1"


def test_resolve_entry_pattern_plugin_id_falls_back_to_manifest():
    compose = ComposeResult(
        mas_id="test",
        mas_config={},
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="test",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[],
        ),
        plan=PlacementPlan(),
    )
    manifest = {"spec": {"design_pattern": {"type": "plan-execute"}}}
    assert resolve_entry_pattern_plugin_id(compose, "alpha", entry_manifest=manifest) == "plan_execute@v1"


def test_is_sequential_workflow_rejects_dynamic():
    dynamic = {
        "spec": {
            "workflow": {
                "entry": "moderator",
                "nodes": [{"id": "moderator", "delegates_to": ["a"]}],
            }
        }
    }
    assert is_sequential_workflow(dynamic, 2) is False


def test_is_sequential_workflow_rejects_dynamic_with_edges():
    dynamic = {
        "spec": {
            "workflow": {
                "type": "dynamic",
                "entry": "moderator",
                "edges": [{"from": "moderator", "to": "worker"}],
                "nodes": [{"id": "moderator"}, {"id": "worker"}],
            }
        }
    }
    assert is_sequential_workflow(dynamic, 2) is False


def test_is_sequential_workflow_rejects_untyped_graph_with_edges():
    graph = {
        "spec": {
            "workflow": {
                "entry": "moderator",
                "edges": [{"from": "moderator", "to": "worker"}],
                "nodes": [{"id": "moderator"}, {"id": "worker"}],
            }
        }
    }
    assert is_sequential_workflow(graph, 2) is False


def test_sequential_workflow_payload_uses_explicit_edges_only():
    mas = {
        "spec": {
            "workflow": {
                "type": "sequential",
                "entry": "a",
                "nodes": [{"id": "a", "delegates_to": ["b"]}, {"id": "b"}],
                "edges": [{"from": "a", "to": "b"}],
            }
        }
    }
    payload = sequential_workflow_payload(mas)
    assert payload["edges"] == [{"from": "a", "to": "b"}]

    delegates_only = {
        "spec": {
            "workflow": {
                "type": "sequential",
                "entry": "a",
                "nodes": [{"id": "a", "delegates_to": ["b"]}, {"id": "b"}],
            }
        }
    }
    with pytest.raises(RuntimeError, match="workflow.edges"):
        sequential_workflow_payload(delegates_only)


def test_prepare_delegation_entry_session_sets_driver_agent_id(tmp_path: Path):
    driver = SimpleNamespace(agent_id=None, engine=MagicMock())
    instance = SimpleNamespace(driver=driver)
    compose = ComposeResult(
        mas_id="demo",
        mas_config={"spec": {"workflow": {"entry": "moderator"}}},
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="demo",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[AgentBindSlice(agent_id="moderator", pattern_plugin_id="react@v1")],
        ),
        plan=PlacementPlan(),
    )
    materialized = SimpleNamespace(
        compose=compose,
        materialized=SimpleNamespace(instances={"moderator": instance}),
        mas_base_dir=tmp_path,
    )
    entry_manifest = {"metadata": {"name": "moderator"}, "spec": {}}
    with patch("mas.ctl.executor.mas_session.enrich_entry_agent_for_delegation", return_value=entry_manifest):
        with patch("mas.ctl.executor.mas_session.wire_entry_engine_delegation"):
            prepare_delegation_entry_session(
                materialized,
                entry_id="moderator",
                entry_manifest=entry_manifest,
            )
    assert driver.agent_id == "moderator"


def test_is_mas_manifest_kind_workflow_app(tmp_path: Path):
    for kind in ("workflow", "app"):
        path = tmp_path / f"{kind}.yaml"
        path.write_text(f"kind: {kind}\n", encoding="utf-8")
        assert is_mas_manifest_kind({"kind": kind}, path) is True
        assert mas_manifest_path({"kind": kind}, path) == path
