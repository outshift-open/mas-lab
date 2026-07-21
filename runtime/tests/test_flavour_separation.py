#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for FlavourSeparationValidator.

FT4: a Flavour is deployment posture only. infra_refs, llm, skills, mocking,
and prefer_local must NOT appear — they belong to kind: Agent or the
execution overlay binding. See docs/design/flavour-boundary.md.
"""

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

    def test_deployment_only_spec_passes(self):
        data = _flavour(
            {
                "agent_comm": {"protocol": "agent-local", "mode": "local"},
                "observability": ["native"],
                "tools": {"remote_tools_enabled": False},
            }
        )
        assert not FlavourSeparationValidator.collect_violations(data)


class TestFlavourLlmSkillsMockingRejected:
    def test_llm_block_rejected(self):
        data = _flavour({"llm": {"provider": "openai"}})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("spec.llm belongs in kind: Agent" in v for v in violations)

    def test_api_key_in_flavour_rejected(self):
        data = _flavour({"llm": {"api_key": "sk-secret"}})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("spec.llm belongs in kind: Agent" in v for v in violations)

    def test_empty_llm_block_passes(self):
        data = _flavour({"llm": {}})
        assert not FlavourSeparationValidator.collect_violations(data)

    def test_skills_block_rejected(self):
        data = _flavour({"skills": {"backend": "llamaindex"}})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("spec.skills belongs in kind: Agent" in v for v in violations)

    def test_mocking_block_rejected(self):
        data = _flavour({"mocking": {"enabled": True}})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("spec.mocking belongs in the execution overlay binding" in v for v in violations)

    def test_prefer_local_true_rejected(self):
        data = _flavour({"prefer_local": True})
        violations = FlavourSeparationValidator.collect_violations(data)
        assert any("spec.prefer_local belongs in the execution overlay binding" in v for v in violations)

    def test_prefer_local_false_passes(self):
        data = _flavour({"prefer_local": False})
        assert not FlavourSeparationValidator.collect_violations(data)
