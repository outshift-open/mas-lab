#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for Run Input Envelope (mas.lab.inputs)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mas.lab.inputs import (
    RunInput,
    load_run_input,
    run_input_to_dict,
    validate_run_input_envelope,
)


def test_user_txt_ref_is_raw_text(tmp_path: Path):
    (tmp_path / "prompt.txt").write_text("Note: colons: are fine\n", encoding="utf-8")
    run = load_run_input(
        {
            "id": "t",
            "inputs": {"user": {"ref": "prompt.txt"}},
        },
        base_path=tmp_path,
    )
    assert run.primary_prompt == "Note: colons: are fine"


def test_user_list_of_strings():
    run = load_run_input(
        {
            "id": "m",
            "inputs": {"user": ["First", "Second"]},
        }
    )
    assert run.scripted_queries() == ["First", "Second"]
    assert run_input_to_dict(run)["inputs"]["user"] == ["First", "Second"]


def test_user_ref_object_and_expectations_file(tmp_path: Path):
    (tmp_path / "prompt.yaml").write_text("From file\n", encoding="utf-8")
    (tmp_path / "gt.yaml").write_text(
        yaml.dump({"ground_truth": "Paris"}),
        encoding="utf-8",
    )
    item = {
        "id": "r",
        "inputs": {"user": {"ref": "prompt.yaml"}},
        "expectations": {"ref": "gt.yaml"},
    }
    run = load_run_input(item, base_path=tmp_path)
    assert run.primary_prompt == "From file"
    assert run.expectations["ground_truth"] == "Paris"


def test_catalog_id_ref_not_resolved():
    with pytest.raises(ValueError, match="not resolved yet"):
        load_run_input(
            {
                "id": "x",
                "inputs": {"user": {"id": "library-ioc:prompts@v1#a"}},
            }
        )


def test_memory_seed_kind_file(tmp_path: Path):
    (tmp_path / "seeds.yaml").write_text(
        yaml.dump(
            {
                "apiVersion": "memory-seed/v1",
                "kind": "MemorySeed",
                "entries": [{"key": "policy", "content": "economy only"}],
            }
        ),
        encoding="utf-8",
    )
    run = load_run_input(
        {
            "id": "s",
            "inputs": {
                "user": "Q",
                "memory_seeds": "seeds.yaml",
            },
        },
        base_path=tmp_path,
    )
    assert run.memory_seeds[0]["source"] == "policy"
    assert run.memory_seeds[0]["content"] == "economy only"


def test_validate_user_string_envelope():
    pytest.importorskip("jsonschema")
    validate_run_input_envelope({"inputs": {"user": "Hello"}})


def test_load_run_input_envelope_item():
    item = {
        "id": "002",
        "inputs": {
            "user": "Plan a trip",
            "tool_fixtures": {"routes": []},
        },
        "expectations": {
            "ground_truth": "PolicyDenial",
            "governance": {"expected": "guardrail_triggered"},
        },
    }
    run = load_run_input(item)
    assert run.primary_prompt == "Plan a trip"
    assert run.tool_fixtures == {"routes": []}
    assert run.expectations["governance"]["expected"] == "guardrail_triggered"


def test_load_run_input_empty_item_still_loads():
    run = load_run_input({"id": "001"})
    assert run.primary_prompt == ""


def test_load_run_input_empty_user_list_still_loads():
    run = load_run_input({"id": "001", "inputs": {"user": []}})
    assert run.primary_prompt == ""


def test_legacy_query_item_still_loads():
    run = load_run_input({"id": "001", "query": "what is up?"})
    assert run.primary_prompt == "what is up?"


def test_legacy_prompt_item_still_loads():
    run = load_run_input(
        {
            "id": "001",
            "prompt": "legacy prompt",
            "expected_answer": "4",
            "memory_seeds": [{"source": "s", "content": "seed"}],
        }
    )
    assert run.primary_prompt == "legacy prompt"
    assert run.expectations["ground_truth"] == "4"
    assert run.memory_seeds[0]["source"] == "s"
    assert run.memory_seeds[0]["content"] == "seed"


def test_legacy_role_list_still_loads():
    run = load_run_input(
        {
            "id": "legacy",
            "inputs": {"user": [{"role": "user", "content": "Old shape"}]},
        }
    )
    assert run.primary_prompt == "Old shape"


def test_user_string_is_not_a_path(tmp_path: Path):
    run = load_run_input(
        {
            "id": "t",
            "inputs": {"user": "not-a-file.yaml"},
        },
        base_path=tmp_path,
    )
    assert run.primary_prompt == "not-a-file.yaml"


def test_load_run_input_scenario_inputs_merge():
    item = {
        "id": "003",
        "inputs": {"user": "Q"},
    }
    scenario = {
        "inputs": {"memory_seeds": [{"source": "s", "content": "seed"}]},
        "expectations": {"ground_truth": "42"},
    }
    run = load_run_input(item, scenario=scenario)
    assert run.memory_seeds == [{"source": "s", "content": "seed"}]
    assert run.expectations["ground_truth"] == "42"


def test_load_run_input_scenario_memory_seed_merge():
    item = {
        "id": "003",
        "inputs": {"user": "Q"},
    }
    scenario = {"spec": {"memory_seed": [{"source": "s", "content": "seed"}]}}
    run = load_run_input(item, scenario=scenario)
    assert run.memory_seeds == [{"source": "s", "content": "seed"}]


def test_load_run_input_memory_seeds_from_file(tmp_path: Path):
    seed_file = tmp_path / "seeds.yaml"
    seed_file.write_text(
        yaml.dump([{"source": "file", "content": "from disk"}]),
        encoding="utf-8",
    )
    item = {
        "id": "004",
        "inputs": {
            "user": "Q",
            "memory_seeds": "seeds.yaml",
        },
    }
    run = load_run_input(item, base_path=tmp_path)
    assert run.memory_seeds == [{"source": "file", "content": "from disk"}]


def test_scripted_queries_multi_turn():
    run = RunInput(
        user=[
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
        ],
        hitl=[{"role": "hitl", "content": "Operator fix"}],
    )
    assert run.scripted_queries() == ["First", "Second", "Operator fix"]


def test_run_input_round_trip_dict():
    run = RunInput(
        user=[{"role": "user", "content": "Hi"}],
        hitl=[{"role": "hitl", "content": "OK"}],
        expectations={"ground_truth": "x"},
    )
    envelope = run_input_to_dict(run)
    assert envelope["inputs"]["user"] == "Hi"
    assert envelope["inputs"]["hitl"] == ["OK"]
    envelope = run_input_to_dict(run)
    pytest.importorskip("jsonschema")
    validate_run_input_envelope(envelope)
    reloaded = load_run_input({"id": "r", **envelope})
    assert reloaded.primary_prompt == "Hi"
    assert reloaded.hitl[0]["content"] == "OK"


def test_tool_fixtures_path_and_fragment(tmp_path: Path):
    body = tmp_path / "tool_fixtures.yaml"
    body.write_text(
        yaml.dump(
            {
                "items": [
                    {"id": "a", "services": {"svc": {}}},
                    {"id": "b", "services": {"other": {}}},
                ]
            }
        ),
        encoding="utf-8",
    )
    item = {
        "id": "x",
        "inputs": {
            "user": "Q",
            "tool_fixtures": "tool_fixtures.yaml#a",
        },
        "expectations": {"correct_action": {"action": "rollback"}},
    }
    run = load_run_input(item, base_path=tmp_path)
    assert run.tool_fixtures["id"] == "a"
    assert "svc" in run.tool_fixtures["services"]
    assert run.expectations["correct_action"]["action"] == "rollback"


def test_tool_fixtures_fragment_falls_back_to_next_candidate_key(tmp_path: Path):
    """A miss on one candidate list key (``items``) must fall through to the
    next (``fixtures``) instead of raising immediately."""
    body = tmp_path / "tool_fixtures.yaml"
    body.write_text(
        yaml.dump(
            {
                "items": [{"id": "other", "services": {}}],
                "fixtures": [{"id": "target", "services": {"svc": {}}}],
            }
        ),
        encoding="utf-8",
    )
    item = {
        "id": "x",
        "inputs": {
            "user": "Q",
            "tool_fixtures": "tool_fixtures.yaml#target",
        },
    }
    run = load_run_input(item, base_path=tmp_path)
    assert run.tool_fixtures["id"] == "target"
    assert "svc" in run.tool_fixtures["services"]


def test_tool_fixtures_by_tool_mapping(tmp_path: Path):
    (tmp_path / "scene.yaml").write_text(
        yaml.dump({"id": "scene", "services": {"edge-gateway": {}}}),
        encoding="utf-8",
    )
    item = {
        "id": "x",
        "inputs": {
            "user": "Q",
            "tool_fixtures": {
                "by_tool": {
                    "*": "scene.yaml",
                    "query_db": {"rows": []},
                }
            },
        },
    }
    run = load_run_input(item, base_path=tmp_path)
    assert run.tool_fixtures["by_tool"]["*"]["id"] == "scene"
    assert run.tool_fixtures["by_tool"]["query_db"] == {"rows": []}


def test_overlay_incident_fixture_fills_missing_tool_fixtures(tmp_path: Path):
    (tmp_path / "scene.yaml").write_text(
        "services:\n  edge-gateway: {}\n",
        encoding="utf-8",
    )
    run = load_run_input(
        {"id": "x", "inputs": {"user": "Q"}},
        scenario={
            "spec": {
                "patch": {"params": {"incident_fixture": "scene.yaml"}},
            }
        },
        base_path=tmp_path,
    )
    assert "edge-gateway" in run.tool_fixtures["services"]


def test_overlay_incident_fixture_does_not_override_item(tmp_path: Path):
    (tmp_path / "item.yaml").write_text("services:\n  item-svc: {}\n", encoding="utf-8")
    (tmp_path / "overlay.yaml").write_text("services:\n  overlay-svc: {}\n", encoding="utf-8")
    run = load_run_input(
        {
            "id": "x",
            "inputs": {"user": "Q", "tool_fixtures": "item.yaml"},
        },
        scenario={
            "spec": {"patch": {"params": {"incident_fixture": "overlay.yaml"}}},
        },
        base_path=tmp_path,
    )
    assert "item-svc" in run.tool_fixtures["services"]
    (tmp_path / "metrics.yaml").write_text(
        yaml.dump({"id": "m", "services": {"edge-gateway": {}}}),
        encoding="utf-8",
    )
    item = {
        "id": "x",
        "inputs": {
            "user": "Q",
            "tool_fixtures": [
                {"tool": "get_metrics", "ref": "metrics.yaml"},
                {"tools": ["get_logs"], "ref": "metrics.yaml"},
            ],
        },
    }
    run = load_run_input(item, base_path=tmp_path)
    assert run.tool_fixtures["by_tool"]["get_metrics"]["id"] == "m"
    assert run.tool_fixtures["by_tool"]["get_logs"]["id"] == "m"


def test_tool_fixtures_data_alias_and_by_tool_ref(tmp_path: Path):
    (tmp_path / "scene.yaml").write_text("id: scene\nservices: {}\n", encoding="utf-8")
    run = load_run_input(
        {
            "id": "x",
            "inputs": {
                "user": "Q",
                "tool_fixtures": [
                    {"tool": "get_metrics", "data": "scene.yaml"},
                ],
            },
        },
        base_path=tmp_path,
    )
    assert run.tool_fixtures["by_tool"]["get_metrics"]["id"] == "scene"
    run2 = load_run_input(
        {
            "id": "y",
            "inputs": {
                "user": "Q",
                "tool_fixtures": {
                    "by_tool": {"query_db": {"data": "scene.yaml"}},
                },
            },
        },
        base_path=tmp_path,
    )
    assert run2.tool_fixtures["by_tool"]["query_db"]["id"] == "scene"
