#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance binding — plugin list only."""

import pytest

from mas.ctl.manifest.spec_bindings import SpecBindingError, parse_governance


def test_governance_plugin_list():
    raw = [{"sample_governance": {"hitl_on_tool": True, "policies": []}}]
    binding = parse_governance(raw)
    assert binding.plugins == ["sample_governance"]
    assert binding.hitl_on_tool is True


def test_governance_flat_dict_rejected():
    with pytest.raises(SpecBindingError, match="plugin list"):
        parse_governance({"hitl_on_tool": True})
