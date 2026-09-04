#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Overlay merge tests."""

from mas.ctl.overlay.merge import (
    OverlayTargetError,
    apply_merge_patch,
    merge_context_chunk,
    merge_context_map,
    merge_overlay,
    overlay_runtime_semantics,
)


def _overlay(patch: dict, *, name: str = "test", target_kind: str = "Agent") -> dict:
    return {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": name},
        "spec": {"target": {"kind": target_kind}, "patch": patch},
    }


def test_merge_tools_overlay():
    base = {"spec": {"models": [{"model": "gpt-4"}]}}
    merged = merge_overlay(base, _overlay({"tools": {"$op": {"add": ["calc"]}}}))
    assert "calc" in merged["spec"]["tools"]


def test_merge_patch_format():
    base = {"spec": {"context": {"role": "base"}}}
    merged = merge_overlay(base, _overlay({"tools": {"$op": {"add": ["web"]}}}))
    assert "web" in merged["spec"]["tools"]


def test_merge_tools_dedupes():
    base = {"spec": {"tools": ["calc"]}}
    merged = merge_overlay(base, _overlay({"tools": {"$op": {"add": ["calc", "web"]}}}))
    assert merged["spec"]["tools"] == ["calc", "web"]


def test_merge_design_pattern():
    base = {"spec": {}}
    merged = merge_overlay(base, _overlay({"design_pattern": {"type": "cot"}}))
    assert merged["spec"]["design_pattern"]["type"] == "cot"


def test_merge_context_dict():
    base = {"spec": {"context": {"role": "a"}}}
    merged = merge_overlay(base, _overlay({"context": {"intent": "b"}}))
    assert merged["spec"]["context"] == {"role": "a", "intent": "b"}


def test_merge_context_op_add_appends_without_duplicating_base_text():
    base = {"spec": {"context": {"role": "You are a triage agent."}}}
    merged = merge_overlay(
        base, _overlay({"context": {"role": {"$op": {"add": ["Escalate P1s immediately."]}}}})
    )
    assert merged["spec"]["context"]["role"] == [
        "You are a triage agent.",
        "Escalate P1s immediately.",
    ]


def test_merge_context_op_remove():
    base = {"spec": {"context": {"role": ["a", "b", "c"]}}}
    merged = merge_overlay(base, _overlay({"context": {"role": {"$op": {"remove": ["b"]}}}}))
    assert merged["spec"]["context"]["role"] == ["a", "c"]


def test_merge_context_op_replace():
    base = {"spec": {"context": {"role": ["a", "b"]}}}
    merged = merge_overlay(base, _overlay({"context": {"role": {"$op": {"replace": ["z"]}}}}))
    assert merged["spec"]["context"]["role"] == ["z"]


def test_merge_context_op_clear():
    base = {"spec": {"context": {"role": ["a", "b"]}}}
    merged = merge_overlay(base, _overlay({"context": {"role": {"$op": {"clear": True}}}}))
    assert merged["spec"]["context"]["role"] == []


def test_merge_context_plain_value_still_fully_replaces_chunk():
    base = {"spec": {"context": {"role": "old role"}}}
    merged = merge_overlay(base, _overlay({"context": {"role": "new role"}}))
    assert merged["spec"]["context"]["role"] == "new role"


def test_merge_context_plain_array_still_fully_replaces_chunk():
    """A plain array patch (no `$op`) replaces the chunk wholesale, same as a
    plain string always has -- only `$op` opts into add/remove fragment merging."""
    base = {"spec": {"context": {"role": ["a", "b"]}}}
    merged = merge_overlay(base, _overlay({"context": {"role": ["c", "d"]}}))
    assert merged["spec"]["context"]["role"] == ["c", "d"]


def test_merge_context_chunk_add_appends_without_duplicating():
    merged = merge_context_chunk("You are a triage agent.", {"$op": {"add": ["Be concise."]}})
    assert merged == ["You are a triage agent.", "Be concise."]


def test_merge_context_chunk_add_is_idempotent():
    merged = merge_context_chunk(["a", "b"], {"$op": {"add": ["b", "c"]}})
    assert merged == ["a", "b", "c"]


def test_merge_context_chunk_remove():
    merged = merge_context_chunk(["a", "b", "c"], {"$op": {"remove": ["b"]}})
    assert merged == ["a", "c"]


def test_merge_context_chunk_replace():
    merged = merge_context_chunk(["a", "b"], {"$op": {"replace": ["z"]}})
    assert merged == ["z"]


def test_merge_context_chunk_clear():
    merged = merge_context_chunk(["a", "b"], {"$op": {"clear": True}})
    assert merged == []


def test_merge_context_chunk_plain_string_value_replaces():
    """No `$op` sugar -- implicit full replace, same ergonomics as list_ops."""
    assert merge_context_chunk("old role", "new role") == "new role"


def test_merge_context_chunk_plain_array_value_replaces():
    """A plain array (no `$op`) is also an implicit full replace, not an add --
    `$op` is what opts into fragment-level merging; a bare list is a new chunk
    value, same as a bare string or {ref} would be."""
    merged = merge_context_chunk(["a", "b"], ["c", "d"])
    assert merged == ["c", "d"]


def test_merge_context_chunk_plain_array_replaces_existing_string_chunk():
    merged = merge_context_chunk("old role", ["fragment one", "fragment two"])
    assert merged == ["fragment one", "fragment two"]


def test_merge_context_map_adds_new_key_and_patches_existing():
    base = {"role": "You are a triage agent."}
    patch = {"role": {"$op": {"add": ["Be concise."]}}, "intent": "Stay on task."}
    merged = merge_context_map(base, patch)
    assert merged == {
        "role": ["You are a triage agent.", "Be concise."],
        "intent": "Stay on task.",
    }


def test_merge_skills():
    base = {"spec": {"skills": ["s1"]}}
    merged = merge_overlay(base, _overlay({"skills": {"$op": {"add": ["s1", "s2"]}}}))
    assert merged["spec"]["skills"] == ["s1", "s2"]


def test_merge_tools_remove_via_op_remove():
    """tools_remove (a separate attribute) was removed as a concept: tools
    itself already supports {"$op": {"remove": [...]}} (list_ops), the same
    subtraction without a second, separately-named attribute."""
    base = {"spec": {"tools": ["calc", "web-search"]}}
    merged = merge_overlay(base, _overlay({"tools": {"$op": {"remove": ["web-search"]}}}))
    assert merged["spec"]["tools"] == ["calc"]


def test_merge_plugins_patch_is_rejected() -> None:
    import pytest

    base = {"spec": {"plugins": [{"name": "p1", "enabled": True}]}}
    with pytest.raises(OverlayTargetError, match="Unsupported Agent overlay patch field"):
        merge_overlay(base, _overlay({"plugins": [{"name": "p1", "enabled": False}]}))


def test_merge_memory_and_seed():
    base = {"spec": {"memory_seed": [{"key": "k1", "content": "c1"}]}}
    merged = merge_overlay(
        base,
        _overlay({"memory": "letta", "memory_seed": {"$op": {"add": [{"key": "k2", "content": "c2"}]}}}),
    )
    assert merged["spec"]["memory"] == "letta"
    assert len(merged["spec"]["memory_seed"]) == 2


def test_merge_params_overlay_field():
    """params was a real, consumed field (params_sidecar.py, infra_pipeline.py)
    with no base-schema declaration until the Agent overlay-patch/base-schema
    unification -- confirms it's now a real, mergeable field end to end."""
    base = {"spec": {}}
    merged = merge_overlay(base, _overlay({"params": {"foo": "bar"}}))
    assert merged["spec"]["params"] == {"foo": "bar"}


def test_merge_context_policy_is_rejected_as_dead_field():
    """context_policy had zero consumers anywhere in the repo -- removed as
    dead schema during the Agent overlay-patch/base-schema unification."""
    import pytest

    base = {"spec": {}}
    with pytest.raises(OverlayTargetError, match="Unsupported Agent overlay patch field"):
        merge_overlay(base, _overlay({"context_policy": {"foo": "bar"}}))


def test_merge_mas_params_field_was_a_real_gap_now_closed():
    """mas.schema.yaml didn't declare spec.params at all even though
    merge_mas_overlay always wrote patched params under spec.params --
    closed as part of the MAS overlay-patch/base-schema unification
    (same pattern as Agent's params gap)."""
    base = {"kind": "MAS", "spec": {}}
    merged = merge_overlay(base, _overlay({"params": {"foo": "bar"}}, target_kind="MAS"))
    assert merged["spec"]["params"] == {"foo": "bar"}


def test_merge_mas_capabilities_field_was_a_real_gap_now_closed():
    base = {"kind": "MAS", "spec": {}}
    merged = merge_overlay(base, _overlay({"capabilities": {"streaming": True}}, target_kind="MAS"))
    assert merged["spec"]["capabilities"] == {"streaming": True}


def test_merge_mas_governance_is_rejected_as_a_dead_field():
    """MAS-level governance was special-cased out of the generic merge
    dispatch but never had an actual merge implementation -- patching it
    was a silent no-op with zero test coverage. Removed as dead, mirroring
    context_policy's removal from the Agent overlay-patch fragment."""
    import pytest

    base = {"kind": "MAS", "spec": {}}
    with pytest.raises(OverlayTargetError, match="Unsupported MAS overlay patch field"):
        merge_overlay(base, _overlay({"governance": ["policy-a"]}, target_kind="MAS"))


def test_merge_working_memory_persistent():
    base = {"spec": {}}
    merged = merge_overlay(base, _overlay({"working_memory": {"persistent": True}}))
    assert merged["spec"]["working_memory"] == {"persistent": True}


def test_merge_working_memory_persistent_merges_over_existing_block():
    base = {"spec": {"working_memory": {"persistent": True}}}
    merged = merge_overlay(base, _overlay({"working_memory": {"persistent": False}}))
    assert merged["spec"]["working_memory"] == {"persistent": False}


def test_merge_governance_null_removes_key():
    base = {"spec": {"governance": ["policy-a", {"policy-b": {}}]}}
    merged = merge_overlay(base, _overlay({"governance": {"$op": {"remove": ["policy-a"], "add": ["policy-c"]}}}))
    assert merged["spec"]["governance"] == [{"policy-b": {}}, "policy-c"]


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
                    "memory_seed": {"$op": {"add": [{"key": "f001", "content": "seed"}]}},
                }
            }
        },
        target_kind="MAS",
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
        {"agents": {"moderator": {"context": {"role": "patched role"}}}},
        target_kind="MAS",
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
    merged = merge_overlay(base, _overlay({"agents_remove": {"$op": {"add": ["helper"]}}}, target_kind="MAS"))
    agents = merged["spec"]["agency"]["agents"]
    assert len(agents) == 1
    assert agents[0]["id"] == "moderator"


def test_merge_mas_overlay_rejects_unsupported_patch_field() -> None:
    import pytest

    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [
                    {"id": "a", "ref": "agents/a.yaml"},
                ]
            }
        },
    }
    overlay = _overlay({"design_pattern": {"type": "cot"}}, target_kind="MAS")
    with pytest.raises(OverlayTargetError, match="Unsupported MAS overlay patch field"):
        merge_overlay(base, overlay)


def test_merge_tools_explicit_ops_replace_add_remove_clear():
    base = {"spec": {"tools": ["calc", "web-search"]}}
    merged = merge_overlay(base, _overlay({"tools": {"$op": {"remove": ["calc"], "add": ["memory-search"]}}}))
    assert merged["spec"]["tools"] == ["web-search", "memory-search"]

    cleared = merge_overlay(base, _overlay({"tools": {"$op": {"clear": True}}}))
    assert cleared["spec"]["tools"] == []

    replaced = merge_overlay(base, _overlay({"tools": {"$op": {"replace": ["memory-search"]}}}))
    assert replaced["spec"]["tools"] == ["memory-search"]


def test_merge_skills_explicit_ops():
    base = {"spec": {"skills": ["s1", "s2"]}}
    merged = merge_overlay(base, _overlay({"skills": {"$op": {"remove": ["s1"], "add": ["s3"]}}}))
    assert merged["spec"]["skills"] == ["s2", "s3"]


def test_merge_memory_seed_explicit_ops():
    base = {"spec": {"memory_seed": [{"key": "k1", "content": "c1"}]}}
    merged = merge_overlay(base, _overlay({"memory_seed": {"$op": {"add": [{"key": "k2", "content": "c2"}]}}}))
    assert merged["spec"]["memory_seed"] == [
        {"key": "k1", "content": "c1"},
        {"key": "k2", "content": "c2"},
    ]


def test_merge_mas_agents_remove_explicit_ops():
    base = {
        "kind": "MAS",
        "spec": {
            "agency": {
                "agents": [
                    {"id": "moderator", "ref": "agents/moderator.yaml"},
                    {"id": "helper", "ref": "agents/helper.yaml"},
                ]
            }
        },
    }
    merged = merge_overlay(base, _overlay({"agents_remove": {"$op": {"add": ["helper"]}}}, target_kind="MAS"))
    assert [a["id"] for a in merged["spec"]["agency"]["agents"]] == ["moderator"]


def test_composition_tools_replace_dominates_previous_add() -> None:
    base = {"spec": {"tools": ["a"]}}
    merged_once = merge_overlay(base, _overlay({"tools": {"$op": {"add": ["b"]}}}))
    merged_twice = merge_overlay(merged_once, _overlay({"tools": {"$op": {"replace": ["c"]}}}))
    assert merged_twice["spec"]["tools"] == ["c"]


def test_composition_tools_clear_then_add_is_deterministic() -> None:
    base = {"spec": {"tools": ["a", "b"]}}
    merged_once = merge_overlay(base, _overlay({"tools": {"$op": {"clear": True}}}))
    merged_twice = merge_overlay(merged_once, _overlay({"tools": {"$op": {"add": ["c"]}}}))
    assert merged_twice["spec"]["tools"] == ["c"]


def test_composition_control_merge_then_replace_is_deterministic() -> None:
    base = {"spec": {"control": {"budget": {"max_tokens": 10}}}}
    merged_once = merge_overlay(base, _overlay({"control": {"$op": {"merge": {"rate_limiter": {"requests_per_minute": 5}}}}}))
    merged_twice = merge_overlay(merged_once, _overlay({"control": {"$op": {"replace": {"budget": {"max_tokens": 99}}}}}))
    assert merged_twice["spec"]["control"] == {"budget": {"max_tokens": 99}}


def test_list_field_accepts_implicit_array_replace() -> None:
    base = {"spec": {"skills": ["s1"]}}
    merged = merge_overlay(base, _overlay({"skills": ["s2"]}))
    assert merged["spec"]["skills"] == ["s2"]


def test_runtime_semantics_registry_covers_non_trivial_agent_fields() -> None:
    semantics = overlay_runtime_semantics()
    agent = semantics["Agent"]
    for field in (
        "tools",
        "skills",
        "memory_seed",
        "infra_refs",
        "observability",
        "governance",
        "control",
    ):
        assert field in agent
    assert "Infra" in semantics


def test_merge_infra_overlay_json_merge_patch_semantics() -> None:
    base = {
        "apiVersion": "mas/v1",
        "kind": "Infra",
        "metadata": {"name": "default"},
        "spec": {
            "proxy": {"api_base": "https://api.example", "api_key_env": "OPENAI_API_KEY"},
            "models": {"allowed": ["gpt-4o-mini"]},
            "tools": {"web": {"enabled": True}},
        },
    }
    ov = _overlay(
        {
            "proxy": {"api_base": "https://new.example"},
            "models": {"allowed": ["gpt-4o"]},
            "tools": {"web": None, "calc": {"enabled": True}},
        },
        target_kind="Infra",
    )
    merged = merge_overlay(base, ov)
    assert merged["spec"]["proxy"] == {
        "api_base": "https://new.example",
        "api_key_env": "OPENAI_API_KEY",
    }
    assert merged["spec"]["models"] == {"allowed": ["gpt-4o"]}
    assert merged["spec"]["tools"] == {"calc": {"enabled": True}}
