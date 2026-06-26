#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for ApplicationRunner registry and controller API."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_application_runner_registry_mas():
    from mas.lab.runners.registry import ApplicationRunnerRegistry

    ApplicationRunnerRegistry.reset()
    available = ApplicationRunnerRegistry.available()
    assert "mas" in available
    runner = ApplicationRunnerRegistry.get("mas")
    assert runner.runner_id == "mas"


def test_manifest_store_discovers_labs():
    from mas.lab.controller.manifest_store import ManifestStore

    with tempfile.TemporaryDirectory() as tmp:
        ws_root = Path(tmp)
        labs = ws_root / "labs"
        lab = labs / "demo.lab"
        (lab / "experiments").mkdir(parents=True)
        (lab / "experiments" / "smoke.yaml").write_text(
            "metadata:\n  name: smoke\n  description: test\n",
            encoding="utf-8",
        )
        store = ManifestStore(workspace=None)
        store._libraries = {"demo": lab}
        exps = store.list_yaml_resources("demo", "experiments")
        assert len(exps) == 1
        assert exps[0]["name"] == "smoke"


def test_controller_api_submit_benchmark_worker():
    from mas.lab.controller.api import ControllerAPI

    api = ControllerAPI()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("metadata:\n  name: dry\n")
        exp_path = fh.name
    try:
        result = api.submit_benchmark(
            {"experiment_yaml": exp_path, "dry_run": True, "progress": False}
        )
        assert "worker_id" in result
        assert api.get_worker(result["worker_id"]) is not None
    finally:
        Path(exp_path).unlink(missing_ok=True)
