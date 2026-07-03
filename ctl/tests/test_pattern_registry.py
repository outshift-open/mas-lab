#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from mas.ctl.compose.pattern_registry import resolve_design_pattern_registry_id


def test_resolve_design_pattern_cot():
    assert resolve_design_pattern_registry_id({"type": "cot"}) == "cot@v1"


def test_resolve_design_pattern_plan_execute_alias():
    assert resolve_design_pattern_registry_id({"type": "plan-execute"}) == "plan_execute@v1"


def test_resolve_design_pattern_defaults_react():
    assert resolve_design_pattern_registry_id(None) == "react@v1"
