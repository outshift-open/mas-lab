#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for local-inproc ControllerContract plugin."""

from mas.lab.contracts.controller import discover_controllers, get_controller


def test_local_inproc_registered():
    plugins = discover_controllers()
    assert "local-inproc" in plugins


def test_local_inproc_deploy_probe_teardown():
    ctrl = get_controller("local-inproc")
    manifest = {"metadata": {"name": "trip-planner"}, "spec": {"agents": [{"llm_model": "gpt-4o"}]}}
    result = ctrl.deploy(manifest)
    assert result.success
    snap = ctrl.probe()
    assert snap.healthy
    assert len(snap.agents) == 1
    ctrl.teardown("trip-planner")
    assert len(ctrl.probe().agents) == 0
