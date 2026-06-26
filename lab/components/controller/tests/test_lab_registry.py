#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for unified LabRegistry."""
from __future__ import annotations

from pathlib import Path

from mas.lab.controller.lab_registry import (
    CANONICAL_DEFAULT_DP,
    CANONICAL_DEFAULT_MODEL,
    LabRegistry,
    get_lab_registry,
    reset_lab_registry,
)


def test_agent_defaults():
    reset_lab_registry()
    reg = get_lab_registry()
    defaults = reg.agent_defaults()
    assert defaults["design_pattern"]["type"] == CANONICAL_DEFAULT_DP
    assert defaults["models"][0]["model"] == reg.default_model()
    reset_lab_registry()


def test_catalog_includes_runtime_and_steps():
    reset_lab_registry()
    reg = get_lab_registry()
    catalog = reg.catalog()
    assert "runtime" in catalog
    assert "spec" in catalog
    assert "design_pattern" in catalog["spec"]
    assert "pipeline_steps" in catalog
    assert "defaults" in catalog
    assert catalog["defaults"]["models"][0]["model"]
    reset_lab_registry()


def test_list_spec_design_pattern():
    reset_lab_registry()
    reg = get_lab_registry()
    patterns = reg.list("design_pattern")
    assert isinstance(patterns, list)
    if patterns:
        assert "urn" in patterns[0]
    reset_lab_registry()


def test_resolve_default_model_never_empty():
    from mas.ctl.session.engine_factory import resolve_model_name

    assert resolve_model_name({"spec": {"llm": {"model": None}}}, None)
    assert resolve_model_name(None, None)


def test_default_model_is_gpt4o_mini():
    reset_lab_registry()
    reg = get_lab_registry()
    assert reg.default_model() == CANONICAL_DEFAULT_MODEL or reg.default_model()
    reset_lab_registry()


def test_list_experiments_lab_layout(tmp_path: Path):
    lab = tmp_path / "demo.lab"
    lab.mkdir()
    (lab / "experiment.yaml").write_text(
        "experiment:\n  name: root-exp\n  description: root\n",
        encoding="utf-8",
    )
    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"demo": lab}
    exps = reg.list_experiments("demo")
    assert any(e["name"] == "root-exp" for e in exps)
    reset_lab_registry()
