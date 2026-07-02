#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS → entry agent manifest merge."""

from pathlib import Path

import pytest
import yaml

from mas.ctl.manifest.mas_agent_merge import enrich_entry_agent_for_delegation, wire_entry_engine_delegation
from mas.ctl.manifest.spec_bindings import SpecBindingError
from mas.runtime.engine.tools import openai_tools, resolve_manifest_tool_refs


def test_enrich_entry_agent_injects_workflow_without_collaboration():
    agent = {
        "metadata": {"name": "entry"},
        "spec": {"role": {"description": "lead"}},
    }
    mas = {
        "spec": {
            "workflow": {
                "entry": "entry",
                "type": "dynamic",
                "nodes": [{"id": "entry", "delegates_to": ["alpha", "beta"]}],
            }
        }
    }
    enriched = enrich_entry_agent_for_delegation(agent, mas)
    assert enriched["spec"]["workflow"]["entry"] == "entry"
    assert "collaboration" not in enriched.get("spec", {})
    tools = openai_tools(enriched, agent_id="entry")
    names = [t["function"]["name"] for t in tools]
    assert "delegate_to_alpha" in names
    assert "delegate_to_beta" in names


def test_enrich_rejects_unsupported_collaboration():
    agent = {
        "metadata": {"name": "entry"},
        "spec": {"collaboration": {"type": "llm-delegator"}},
    }
    mas = {"spec": {"workflow": {"entry": "entry", "nodes": [{"id": "entry"}]}}}
    with pytest.raises(SpecBindingError):
        enrich_entry_agent_for_delegation(agent, mas)


def test_resolve_tool_refs_from_yaml(tmp_path: Path):
    tool_yaml = tmp_path / "run_action.tool.yaml"
    tool_yaml.write_text(
        yaml.safe_dump(
            {
                "metadata": {"name": "run_action"},
                "spec": {"description": "act"},
            }
        ),
        encoding="utf-8",
    )
    agent = {"spec": {"tools": [{"ref": "run_action.tool.yaml"}]}}
    resolved = resolve_manifest_tool_refs(agent, tmp_path)
    assert resolved["spec"]["tools"][0]["name"] == "run_action"


def test_resolve_tool_refs_rejects_path_outside_base_dir(tmp_path: Path):
    outside = tmp_path.parent / "outside.tool.yaml"
    outside.write_text(
        yaml.safe_dump({"metadata": {"name": "evil"}, "spec": {}}),
        encoding="utf-8",
    )
    agent = {"spec": {"tools": [{"ref": f"../{outside.name}"}]}}
    resolved = resolve_manifest_tool_refs(agent, tmp_path)
    item = resolved["spec"]["tools"][0]
    assert "name" not in item


def test_resolve_tool_refs_does_not_alias_original_manifest(tmp_path: Path):
    tool_yaml = tmp_path / "run_action.tool.yaml"
    tool_yaml.write_text(
        yaml.safe_dump({"metadata": {"name": "run_action"}, "spec": {"description": "act"}}),
        encoding="utf-8",
    )
    agent = {"spec": {"tools": [{"ref": "run_action.tool.yaml"}]}}
    resolved = resolve_manifest_tool_refs(agent, tmp_path)
    resolved["spec"]["tools"][0]["name"] = "mutated"
    assert agent["spec"]["tools"][0].get("name") != "mutated"


def test_wire_entry_engine_delegation_skips_when_no_peers():
    class _Engine:
        manifest = None
        delegation = "unset"

    engine = _Engine()
    manifest = {
        "metadata": {"name": "solo"},
        "spec": {"workflow": {"entry": "solo", "nodes": [{"id": "solo"}]}},
    }
    wire_entry_engine_delegation(
        engine,
        manifest,
        Path("."),
        run_turn=lambda _a, _t: "",
        entry_agent_id="solo",
    )
    assert engine.delegation is None


def test_wire_entry_engine_delegation_skips_when_delegates_to_empty():
    class _Engine:
        manifest = None
        delegation = "unset"

    engine = _Engine()
    manifest = {
        "metadata": {"name": "leaf"},
        "spec": {
            "workflow": {
                "entry": "leaf",
                "nodes": [
                    {"id": "leaf", "delegates_to": []},
                    {"id": "other", "delegates_to": ["worker"]},
                ],
            }
        },
    }
    wire_entry_engine_delegation(
        engine,
        manifest,
        Path("."),
        run_turn=lambda _a, _t: "",
        entry_agent_id="leaf",
    )
    assert engine.delegation is None


def test_wire_entry_engine_delegation_enables_tool_loop_on_leaf():
    from mas.runtime.engine.infra_pipeline import BidirectionalPipelineEngine
    from mas.runtime.engine.llm_live import LiveLlmEngine

    inner = LiveLlmEngine(manifest=None, use_tool_loop=False)
    engine = BidirectionalPipelineEngine(inner=inner, pipeline_steps=[])

    manifest = {
        "metadata": {"name": "entry"},
        "spec": {
            "workflow": {
                "entry": "entry",
                "nodes": [{"id": "entry", "delegates_to": ["peer"]}],
            },
        },
    }
    wire_entry_engine_delegation(
        engine,
        manifest,
        Path("."),
        run_turn=lambda _a, _t: "ok",
        entry_agent_id="entry",
    )
    assert inner.use_tool_loop is True
    assert inner.delegation is not None
    assert inner.manifest is manifest


def test_reset_engine_delegation_clears_delegate_cache():
    from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator

    from mas.ctl.manifest.mas_agent_merge import reset_engine_delegation

    class _Engine:
        def __init__(self) -> None:
            self.delegation = LlmDelegator(run_turn=lambda _a, _t: "ok")

    engine = _Engine()
    engine.delegation.delegate("peer", "task")
    assert ("peer", "task") in engine.delegation._completed_peers
    reset_engine_delegation(engine)
    assert not engine.delegation._completed_peers
