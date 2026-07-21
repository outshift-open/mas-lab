#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS → entry agent manifest merge."""

from pathlib import Path

import pytest
import yaml

from mas.ctl.manifest.mas_agent_merge import enrich_entry_agent_for_delegation, wire_entry_engine_delegation
from mas.ctl.manifest.spec_bindings import SpecBindingError
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.tools import openai_tools, resolve_manifest_tool_refs


def test_enrich_entry_agent_injects_workflow(tmp_path: Path):
    peer_yaml = tmp_path / "agents" / "alpha.yaml"
    peer_yaml.parent.mkdir(parents=True)
    peer_yaml.write_text(
        yaml.safe_dump(
            {
                "metadata": {"name": "alpha"},
                "spec": {"description": "Alpha specialist for numeric baselines."},
            }
        ),
        encoding="utf-8",
    )
    agent = {
        "metadata": {"name": "entry"},
        "spec": {"description": "Entry orchestrator."},
    }
    mas = {
        "spec": {
            "agents": [{"id": "alpha", "ref": "agents/alpha.yaml"}],
            "workflow": {
                "entry": "entry",
                "type": "dynamic",
                "nodes": [{"id": "entry", "delegates_to": ["alpha", "beta"]}],
            },
        }
    }
    enriched = enrich_entry_agent_for_delegation(
        agent,
        mas,
        mas_base_dir=tmp_path,
    )
    assert enriched["spec"]["workflow"]["entry"] == "entry"
    assert "delegation_peer_descriptions" not in enriched["spec"]
    engine = LiveLlmEngine(manifest=enriched, use_tool_loop=True)
    wire_entry_engine_delegation(
        engine,
        enriched,
        tmp_path,
        run_turn=lambda _a, _t: "ok",
        entry_agent_id="entry",
        mas_config=mas,
        mas_base_dir=tmp_path,
    )
    tools = openai_tools(enriched, agent_id="entry")
    by_name_generic = {t["function"]["name"]: t for t in tools}
    assert by_name_generic["delegate_to_alpha"]["function"]["description"].startswith(
        "Delegate a sub-task to agent alpha."
    )
    tools = openai_tools(
        enriched,
        agent_id="entry",
        peer_descriptions=engine.delegation_peer_descriptions,
    )
    by_name = {t["function"]["name"]: t for t in tools}
    assert "delegate_to_alpha" in by_name
    assert "Alpha specialist" in by_name["delegate_to_alpha"]["function"]["description"]
    assert by_name["delegate_to_beta"]["function"]["description"] == "Delegate a sub-task to agent beta."


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
            self.delegation = LlmDelegator(run_turn=lambda _a, _t, _c, _ccid: "ok")

    engine = _Engine()
    engine.delegation.delegate("peer", "task")
    assert ("peer", "task") in engine.delegation._completed_peers
    reset_engine_delegation(engine)
    assert not engine.delegation._completed_peers


def test_apply_agency_entry_overlay_merges_context_and_tools():
    from mas.ctl.manifest.mas_agent_merge import apply_agency_entry_overlay

    manifest = {
        "metadata": {"name": "moderator"},
        "spec": {"context": {"role": "base prompt"}},
    }
    entry = {
        "id": "moderator",
        "spec": {"context": {"role": "overlay prompt"}},
        "tools": [{"ref": "tools/memory-search.tool.yaml"}],
    }
    merged = apply_agency_entry_overlay(manifest, entry)
    assert merged["spec"]["context"]["role"] == "overlay prompt"
    assert merged["spec"]["tools"] == [{"ref": "tools/memory-search.tool.yaml"}]


def test_apply_agency_entry_overlay_merges_tools_remove():
    from mas.ctl.manifest.mas_agent_merge import apply_agency_entry_overlay

    manifest = {"metadata": {"name": "a"}, "spec": {"tools_remove": ["calc"]}}
    entry = {"id": "a", "tools_remove": ["web-search"]}
    merged = apply_agency_entry_overlay(manifest, entry)
    assert merged["spec"]["tools_remove"] == ["calc", "web-search"]

    manifest2 = {"metadata": {"name": "b"}, "spec": {}}
    entry2 = {
        "id": "b",
        "tools_remove": [{"ref": "samples:tools/calc.tool.yaml"}, "web-search"],
    }
    merged2 = apply_agency_entry_overlay(manifest2, entry2)
    assert merged2["spec"]["tools_remove"] == [
        {"ref": "samples:tools/calc.tool.yaml"},
        "web-search",
    ]


def test_merge_tool_ref_list_keeps_entries_without_key(caplog):
    from mas.ctl.manifest.mas_agent_merge import _merge_tool_ref_list

    caplog.set_level("WARNING")
    merged = _merge_tool_ref_list([], [{"params": {"x": 1}}])
    assert merged == [{"params": {"x": 1}}]
    assert "no ref/name" in caplog.text


def test_apply_agency_entry_overlay_warns_context_type_mismatch(caplog):
    from mas.ctl.manifest.mas_agent_merge import apply_agency_entry_overlay

    caplog.set_level("WARNING")
    manifest = {
        "metadata": {"name": "a"},
        "spec": {"context": {"role": {"ref": "role.md"}}},
    }
    entry = {"id": "a", "spec": {"context": {"role": "inline role"}}}
    merged = apply_agency_entry_overlay(manifest, entry)
    assert merged["spec"]["context"]["role"] == "inline role"
    assert "type str overrides base type dict" in caplog.text


def test_agency_entries_by_id_prefers_agency_bucket():
    from mas.ctl.manifest.mas_agent_merge import _agency_entries_by_id

    mas = {
        "spec": {
            "agency": {"agents": [{"id": "a", "description": "agency wins"}]},
            "agents": [{"id": "a", "description": "spec loses"}],
        }
    }
    entry = _agency_entries_by_id(mas)["a"]
    assert entry["description"] == "agency wins"


def test_wire_entry_engine_delegation_uses_overlay_peer_description(tmp_path: Path):
    peer_yaml = tmp_path / "agents" / "alpha.yaml"
    peer_yaml.parent.mkdir(parents=True)
    peer_yaml.write_text(
        yaml.safe_dump(
            {
                "metadata": {"name": "alpha"},
                "spec": {"description": "Base peer description."},
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "metadata": {"name": "entry"},
        "spec": {
            "workflow": {
                "entry": "entry",
                "nodes": [{"id": "entry", "delegates_to": ["alpha"]}],
            },
        },
    }
    mas = {
        "spec": {
            "agency": {
                "agents": [
                    {
                        "id": "alpha",
                        "ref": "agents/alpha.yaml",
                        "spec": {"description": "Overlay peer description."},
                    }
                ]
            }
        }
    }
    engine = LiveLlmEngine(manifest=manifest, use_tool_loop=True)
    wire_entry_engine_delegation(
        engine,
        manifest,
        tmp_path,
        run_turn=lambda _a, _t: "ok",
        entry_agent_id="entry",
        mas_config=mas,
        mas_base_dir=tmp_path,
    )
    assert engine.delegation_peer_descriptions == {"alpha": "Overlay peer description."}


def test_create_agent_runtime_applies_mas_overlay_context(monkeypatch, tmp_path: Path):
    from mas.ctl.compose.backends.mas_runtime_py import MasRuntimePyKernelBackend
    from mas.ctl.compose.models import AgentBindSlice, ComposedApplication, EffectiveBindManifest
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: WorkspaceConfig({}))
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    infra = resolve_infra_refs(["standard:mock-llm"], anchor=tmp_path)

    agent_yaml = tmp_path / "agents" / "moderator" / "agent.yaml"
    agent_yaml.parent.mkdir(parents=True)
    agent_yaml.write_text(
        yaml.safe_dump(
            {
                "metadata": {"name": "moderator"},
                "spec": {"context": {"role": "base"}, "design_pattern": {"type": "react"}},
            }
        ),
        encoding="utf-8",
    )
    mas = {
        "metadata": {"name": "trip"},
        "spec": {
            "agency": {
                "agents": [
                    {
                        "id": "moderator",
                        "ref": "agents/moderator/agent.yaml",
                        "spec": {"context": {"role": "from overlay"}},
                    }
                ]
            }
        },
    }
    bind = EffectiveBindManifest(
        mas_id="trip",
        spec_revision="",
        runtime_id="mas-runtime-py",
        deployment_name="local-inproc",
        agents=[
            AgentBindSlice(
                agent_id="moderator",
                manifest_path=str(agent_yaml.relative_to(tmp_path)),
            )
        ],
        composed_application=ComposedApplication(mas_id="trip", config=mas),
        mas_base_dir=tmp_path,
    )
    instance = MasRuntimePyKernelBackend(resolved_infra=infra).create_agent_runtime(
        bind, "moderator"
    )
    from mas.runtime.engine.leaf import leaf_engine

    leaf = leaf_engine(instance.driver.engine)
    assert leaf.manifest["spec"]["context"]["role"] == "from overlay"
