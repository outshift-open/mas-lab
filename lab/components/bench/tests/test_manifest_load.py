#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from mas.lab.manifest.load import (
    LOADED_MAS_RAW_KEY,
    is_loaded_mas_raw,
    merge_stacked_entry_agent_manifest,
    should_merge_stacked_entry_agent_config,
)


def test_is_loaded_mas_raw_marker():
    raw = {LOADED_MAS_RAW_KEY: True, "mas": {}, "agents": []}
    assert is_loaded_mas_raw(raw) is True
    assert should_merge_stacked_entry_agent_config(raw) is False


def test_should_merge_stacked_legacy_rows_without_marker():
    stacked = {"mas": {"entry_agent": "a"}, "agents": [{"id": "a"}]}
    assert should_merge_stacked_entry_agent_config(stacked) is True


def test_merge_stacked_applies_pattern_framework_to_design_pattern():
    agent_cfg = {"metadata": {"name": "moderator"}, "spec": {}}
    stacked = {
        "mas": {"entry_agent": "moderator"},
        "agents": [
            {
                "id": "moderator",
                "pattern_framework": "cot",
                "pattern_params": {"max_steps": 3},
            }
        ],
    }
    merged = merge_stacked_entry_agent_manifest(agent_cfg, stacked)
    assert merged["spec"]["design_pattern"]["type"] == "cot"
    assert merged["spec"]["design_pattern"]["config"]["max_steps"] == 3
