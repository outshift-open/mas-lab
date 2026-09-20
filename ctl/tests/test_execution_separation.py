#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from mas.ctl.manifest.spec_bindings import SpecBindingError, validate_agent_spec_bindings
from mas.ctl.validate.separation import check_separation


def test_agent_spec_execution_rejected_by_bindings():
    try:
        validate_agent_spec_bindings({"execution": {"cache": {"enabled": True}}})
    except SpecBindingError as exc:
        assert "spec.execution" in str(exc)
    else:
        raise AssertionError("expected SpecBindingError")


def test_agent_separation_rejects_execution():
    violations = check_separation(
        {"spec": {"execution": {"cache": {"enabled": True}}}},
        "agent",
    )
    assert any("spec.execution" in v for v in violations)


def test_agent_separation_rejects_infra_refs():
    violations = check_separation(
        {"spec": {"infra_refs": ["standard:openai"]}},
        "agent",
    )
    assert any("spec.infra_refs" in v for v in violations)


def test_mas_separation_rejects_infra_refs():
    violations = check_separation(
        {"spec": {"infra_refs": ["standard:openai"]}},
        "mas",
    )
    assert any("spec.infra_refs" in v for v in violations)


def test_overlay_separation_rejects_patch_infra_refs():
    violations = check_separation(
        {"spec": {"patch": {"infra_refs": ["standard:openai"]}}},
        "overlay",
    )
    assert any("spec.patch.infra_refs" in v for v in violations)


def test_overlay_separation_rejects_patch_execution():
    violations = check_separation(
        {"spec": {"patch": {"execution": {"cache": {"enabled": True}}}}},
        "overlay",
    )
    assert any("spec.patch.execution" in v for v in violations)
