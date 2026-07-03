#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Overlay merge tests."""

from mas.ctl.overlay.merge import apply_merge_patch, merge_overlay


def _overlay(patch: dict, *, name: str = "test") -> dict:
    return {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": name},
        "spec": {"patch": patch},
    }


def test_merge_tools_overlay():
    base = {"spec": {"models": [{"model": "gpt-4"}]}}
    merged = merge_overlay(base, _overlay({"tools": ["calc"]}))
    assert "calc" in merged["spec"]["tools"]


def test_merge_patch_format():
    base = {"spec": {"context": {"role": "base"}}}
    merged = merge_overlay(base, _overlay({"tools": ["web"]}))
    assert "web" in merged["spec"]["tools"]


def test_merge_tools_dedupes():
    base = {"spec": {"tools": ["calc"]}}
    merged = merge_overlay(base, _overlay({"tools": ["calc", "web"]}))
    assert merged["spec"]["tools"] == ["calc", "web"]


def test_merge_design_pattern():
    base = {"spec": {}}
    merged = merge_overlay(base, _overlay({"design_pattern": {"type": "cot"}}))
    assert merged["spec"]["design_pattern"]["type"] == "cot"


def test_merge_context_dict():
    base = {"spec": {"context": {"role": "a"}}}
    merged = merge_overlay(base, _overlay({"context": {"intent": "b"}}))
    assert merged["spec"]["context"] == {"role": "a", "intent": "b"}


def test_merge_context_list():
    base = {"spec": {"context": ["a"]}}
    merged = merge_overlay(base, _overlay({"context": ["b"]}))
    assert merged["spec"]["context"] == ["a", "b"]


def test_merge_skills():
    base = {"spec": {"skills": ["s1"]}}
    merged = merge_overlay(base, _overlay({"skills": ["s1", "s2"]}))
    assert merged["spec"]["skills"] == ["s1", "s2"]


def test_merge_tools_remove():
    base = {"spec": {"tools_remove": ["a"]}}
    merged = merge_overlay(base, _overlay({"tools_remove": ["a", "b"]}))
    assert merged["spec"]["tools_remove"] == ["a", "b"]


def test_merge_plugins_by_name():
    base = {"spec": {"plugins": [{"name": "p1", "enabled": True}]}}
    merged = merge_overlay(base, _overlay({"plugins": [{"name": "p1", "enabled": False}]}))
    assert merged["spec"]["plugins"] == [{"name": "p1", "enabled": False}]


def test_merge_memory_and_seed():
    base = {"spec": {"memory_seed": [{"key": "k1", "content": "c1"}]}}
    merged = merge_overlay(
        base,
        _overlay({"memory": "letta", "memory_seed": [{"key": "k2", "content": "c2"}]}),
    )
    assert merged["spec"]["memory"] == "letta"
    assert len(merged["spec"]["memory_seed"]) == 2


def test_merge_governance_null_removes_key():
    base = {"spec": {"governance": {"policy": "strict", "extra": "x"}}}
    merged = merge_overlay(base, _overlay({"governance": {"extra": None, "policy": "permissive"}}))
    assert merged["spec"]["governance"] == {"policy": "permissive"}


def test_merge_metadata_only_overlay_unchanged():
    base = {"metadata": {"name": "a"}, "spec": {"tools": ["x"]}}
    merged = merge_overlay(base, {"metadata": {"name": "ov1"}})
    assert merged["metadata"]["name"] == "a"
    assert merged["spec"]["tools"] == ["x"]


def test_apply_merge_patch_null_deletes():
    target = {"a": 1, "b": 2}
    patch = {"b": None, "c": 3}
    result = apply_merge_patch(target, patch)
    assert result == {"a": 1, "c": 3}


def test_apply_merge_patch_replaces_non_dict_target():
    result = apply_merge_patch([], {"x": 1})
    assert result == {"x": 1}


def test_merge_llm_block():
    base = {"spec": {"llm": {"temperature": 0.1}}}
    merged = merge_overlay(base, _overlay({"llm": {"max_tokens": 100}}))
    assert merged["spec"]["llm"]["temperature"] == 0.1
    assert merged["spec"]["llm"]["max_tokens"] == 100


def test_merge_execution_block():
    base = {"spec": {"execution": {"timeout_s": 30}}}
    merged = merge_overlay(base, _overlay({"execution": {"timeout_s": 60}}))
    assert merged["spec"]["execution"]["timeout_s"] == 60


def test_merge_context_manager_list():
    base = {"spec": {"context_manager": {"include": ["a"]}}}
    merged = merge_overlay(base, _overlay({"context_manager": {"include": ["b"]}}))
    assert merged["spec"]["context_manager"]["include"] == ["a", "b"]


def test_merge_no_spec_in_overlay():
    base = {"spec": {"tools": ["x"]}}
    merged = merge_overlay(base, {"metadata": {"name": "ov"}})
    assert merged["spec"]["tools"] == ["x"]


def test_normalize_rejects_shorthand_overlay():
    import pytest

    from mas.ctl.overlay.normalize import normalize_overlay

    with pytest.raises(ValueError, match="mas/v1"):
        normalize_overlay({"spec": {"tools": ["calc"]}})


def test_merge_mas_overlay_patches_agency_agent_context():
    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [{"id": "moderator", "ref": "agents/moderator/agent.yaml"}]
            }
        },
    }
    overlay = _overlay(
        {
            "agents": {
                "moderator": {
                    "context": {"role": "patched role"},
                    "memory_seed": [{"key": "f001", "content": "seed"}],
                }
            }
        }
    )
    merged = merge_overlay(base, overlay)
    agent = merged["spec"]["agency"]["agents"][0]
    assert agent["spec"]["context"]["role"] == "patched role"
    assert agent["spec"]["memory_seed"] == [{"key": "f001", "content": "seed"}]


def test_merge_mas_overlay_keeps_name_only_agents():
    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [
                    {"id": "moderator", "ref": "agents/moderator.yaml"},
                    {"name": "helper", "ref": "agents/helper.yaml"},
                ]
            }
        },
    }
    overlay = _overlay(
        {"agents": {"moderator": {"context": {"role": "patched role"}}}}
    )
    merged = merge_overlay(base, overlay)
    agents = merged["spec"]["agency"]["agents"]
    assert len(agents) == 2
    by_key = {a.get("id") or a.get("name"): a for a in agents}
    assert by_key["moderator"]["spec"]["context"]["role"] == "patched role"
    assert by_key["helper"]["ref"] == "agents/helper.yaml"


def test_merge_mas_overlay_agents_remove_by_name():
    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [
                    {"id": "moderator", "ref": "agents/moderator.yaml"},
                    {"name": "helper", "ref": "agents/helper.yaml"},
                ]
            }
        },
    }
    merged = merge_overlay(base, _overlay({"agents_remove": ["helper"]}))
    agents = merged["spec"]["agency"]["agents"]
    assert len(agents) == 1
    assert agents[0]["id"] == "moderator"


def test_merge_mas_overlay_global_design_pattern_on_all_agents():
    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [
                    {"id": "a", "ref": "agents/a.yaml"},
                    {"id": "b", "ref": "agents/b.yaml"},
                ]
            }
        },
    }
    overlay = _overlay({"design_pattern": {"type": "cot", "config": {"max_steps": 5}}})
    merged = merge_overlay(base, overlay)
    for agent in merged["spec"]["agency"]["agents"]:
        assert agent["design_pattern"]["type"] == "cot"
        assert agent["design_pattern"]["config"]["max_steps"] == 5


def test_merge_mas_overlay_global_design_pattern_survives_agency_patch():
    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [
                    {"id": "a", "ref": "agents/a.yaml"},
                    {"id": "b", "ref": "agents/b.yaml"},
                ]
            },
            "workflow": {"entry": "a", "type": "dynamic"},
        },
    }
    overlay = _overlay(
        {
            "design_pattern": {"type": "cot", "config": {"max_steps": 3}},
            "agency": {
                "agents": [
                    {"id": "a", "ref": "agents/a.yaml"},
                    {"id": "c", "ref": "agents/c.yaml"},
                ]
            },
        }
    )
    merged = merge_overlay(base, overlay)
    for agent in merged["spec"]["agency"]["agents"]:
        assert agent["design_pattern"]["type"] == "cot"
        assert agent["design_pattern"]["config"]["max_steps"] == 3


def test_merge_mas_overlay_global_design_pattern_on_spec_agents():
    base = {
        "kind": "MAS",
        "spec": {
            "agents": [
                {"id": "x", "ref": "agents/x.yaml"},
                {"id": "y", "ref": "agents/y.yaml"},
            ]
        },
    }
    overlay = _overlay({"design_pattern": {"type": "plan-execute"}})
    merged = merge_overlay(base, overlay)
    for agent in merged["spec"]["agents"]:
        assert agent["design_pattern"]["type"] == "plan-execute"
