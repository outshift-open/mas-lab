#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for FlavourSeparationValidator — infra_refs must NOT appear in flavours."""

from mas.ctl.validate.separation import FlavourSeparationValidator


def _flavour(spec: dict | None = None) -> dict:
    return {
        "apiVersion": "flavour/v1",
        "kind": "Flavour",
        "metadata": {"name": "test"},
        "spec": spec or {},
    }


class TestFlavourInfraRefsRejected:
    def test_infra_refs_list_rejected(self):
        data = _flavour({"infra_refs": ["team:llm-proxy"]})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("infra_refs is forbidden" in v for v in violations)

    def test_infra_ref_string_rejected(self):
        data = _flavour({"infra_ref": "team:llm-proxy"})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("infra_ref is forbidden" in v for v in violations)

    def test_empty_infra_refs_passes(self):
        data = _flavour({"infra_refs": []})
        assert not FlavourSeparationValidator.collect_violations(data)

    def test_no_infra_refs_passes(self):
        data = _flavour({"llm": {"provider": "openai"}})
        assert not FlavourSeparationValidator.collect_violations(data)

    def test_api_key_in_flavour_rejected(self):
        data = _flavour({"llm": {"api_key": "sk-secret"}})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("raw secret" in v for v in violations)
