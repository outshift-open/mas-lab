#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas-ctl compose pipeline."""

from mas.ctl.workspace.config import collect_mas_infra_refs, merge_infra_refs
from mas.ctl.deployment.load import default_deployment


def test_collect_mas_infra_refs():
    config = {"spec": {"infra_refs": ["team:llm-proxy", "team:otel"]}}
    assert collect_mas_infra_refs(config) == ["team:llm-proxy", "team:otel"]

    config2 = {"spec": {"infra_ref": "team:single"}}
    assert collect_mas_infra_refs(config2) == ["team:single"]


def test_merge_infra_refs_order():
    merged = merge_infra_refs(
        mas_refs=["a", "b"],
        workspace_refs=["b", "c"],
        cli_refs=["c", "d"],
    )
    assert merged == ["a", "b", "c", "d"]


def test_default_deployment_local_inproc():
    dep = default_deployment()
    assert dep["spec"]["strategy"] == "local-inproc"
    assert dep["spec"]["bus"]["kind"] == "inproc"
