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
from mas.lab.schemas.paths import lab_schema_dir


def test_load_run_input_envelope_item():
    item = {
        "id": "002",
        "inputs": {
            "user": [{"role": "user", "content": "Plan a trip"}],
            "hitl": [],
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


def test_load_run_input_requires_inputs_block():
    with pytest.raises(ValueError, match="missing required 'inputs'"):
        load_run_input({"id": "001", "prompt": "legacy"})


def test_load_run_input_scenario_inputs_merge():
    item = {
        "id": "003",
        "inputs": {"user": [{"role": "user", "content": "Q"}]},
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
        "inputs": {"user": [{"role": "user", "content": "Q"}]},
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
            "user": [{"role": "user", "content": "Q"}],
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
    pytest.importorskip("jsonschema")
    validate_run_input_envelope(envelope)
    reloaded = load_run_input({"id": "r", **envelope})
    assert reloaded.primary_prompt == "Hi"
    assert reloaded.hitl[0]["content"] == "OK"


def test_run_input_schema_file_exists():
    assert (lab_schema_dir() / "run-input.schema.yaml").is_file()
