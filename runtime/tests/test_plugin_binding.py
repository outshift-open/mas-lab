#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from mas.runtime.spec.plugin_binding import (
    PluginBindingError,
    normalize_plugin_binding,
    normalize_plugin_binding_lenient,
    plugin_binding_id,
    plugin_binding_params,
)


def test_string_shorthand_is_type() -> None:
    assert normalize_plugin_binding("cot", field="spec.design_pattern") == {"type": "cot"}
    assert plugin_binding_id("cot", field="spec.design_pattern") == "cot"


def test_object_form_is_copied() -> None:
    raw = {"type": "summarising", "params": {"keep_turns": 8}}
    out = normalize_plugin_binding(raw, field="spec.context_manager")
    assert out == raw
    assert out is not raw


def test_omission_is_empty() -> None:
    assert normalize_plugin_binding(None, field="spec.assembler") == {}
    assert normalize_plugin_binding("", field="spec.assembler") == {}
    assert plugin_binding_id(None, field="spec.assembler") == ""


def test_params_win_over_config_alias() -> None:
    raw = {"type": "cot", "params": {"max_steps": 3}, "config": {"max_steps": 10}}
    assert plugin_binding_params(raw, field="spec.design_pattern")["max_steps"] == 3


def test_config_alias_used_when_params_omitted() -> None:
    raw = {"type": "cot", "config": {"max_steps": 10}}
    assert plugin_binding_params(raw, field="spec.design_pattern")["max_steps"] == 10


def test_rejects_non_binding() -> None:
    with pytest.raises(PluginBindingError, match="spec.design_pattern"):
        normalize_plugin_binding(["cot"], field="spec.design_pattern")


def test_lenient_form_degrades_instead_of_raising() -> None:
    """Runtime hot paths (ctl already validates at authoring time) never raise."""
    assert normalize_plugin_binding_lenient(["cot"], field="spec.context_manager") == {}
    assert normalize_plugin_binding_lenient(42, field="spec.context_manager") == {}


def test_lenient_form_matches_strict_form_for_well_formed_input() -> None:
    assert normalize_plugin_binding_lenient("cot", field="spec.design_pattern") == {"type": "cot"}
    raw = {"type": "summarising", "params": {"keep_turns": 8}}
    assert normalize_plugin_binding_lenient(raw, field="spec.context_manager") == raw
