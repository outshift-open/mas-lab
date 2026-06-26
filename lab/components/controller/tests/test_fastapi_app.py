#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for FastAPI app (PR #5 integration)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _fake_store(lab: Path):
    from mas.lab.controller.manifest_store import ManifestStore

    store = ManifestStore(workspace=None)
    store._libraries = {"demo": lab}
    return store


@pytest.fixture
def client(sample_lab, monkeypatch):
    from mas.lab.controller import fastapi_app

    monkeypatch.setattr(
        "mas.lab.controller.deps.get_manifest_store",
        lambda: _fake_store(sample_lab),
    )
    return TestClient(fastapi_app.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_libraries(client):
    data = client.get("/api/libraries").json()
    assert len(data["libraries"]) == 1
    assert data["libraries"][0]["dir"] == "demo"


def test_tools_and_skills(client):
    tools = client.get("/api/libraries/demo/tools").json()["tools"]
    assert any(t["name"] == "global/search" for t in tools)
    skills = client.get("/api/libraries/demo/skills").json()["skills"]
    assert skills[0]["name"] == "global/demo-skill"


def test_experiments_crud(client, sample_lab):
    listed = client.get("/api/libraries/demo/experiments").json()["experiments"]
    assert any(e["name"] == "smoke" for e in listed)

    detail = client.get("/api/libraries/demo/experiments/smoke").json()
    assert "smoke" in detail["content"]

    resp = client.post(
        "/api/libraries/demo/experiments",
        json={"name": "newone", "content": "metadata:\n  name: newone\n"},
    )
    assert resp.status_code == 201
    assert (sample_lab / "experiments" / "newone.yaml").exists()

    client.put(
        "/api/libraries/demo/experiments/newone",
        json={"name": "renamed", "content": "metadata:\n  name: renamed\n"},
    )
    assert (sample_lab / "experiments" / "renamed.yaml").exists()

    client.delete("/api/libraries/demo/experiments/renamed")
    assert not (sample_lab / "experiments" / "renamed.yaml").exists()


def test_pipelines_and_overlays(client):
    pipes = client.get("/api/libraries/demo/pipelines").json()["pipelines"]
    assert pipes[0]["name"] == "analysis"

    overlays = client.get("/api/libraries/demo/overlays").json()["overlays"]
    assert overlays[0]["name"] == "baseline"

    detail = client.get("/api/libraries/demo/overlays/baseline").json()
    assert "baseline" in detail["content"]


def test_datasets(client):
    datasets = client.get("/api/libraries/demo/datasets").json()["datasets"]
    assert any(d["name"] == "queries.yaml" for d in datasets)


def test_mas_resources(client, sample_lab):
    listed = client.get("/api/libraries/demo/apps").json()["mas_resources"]
    assert "team" in listed

    detail = client.get("/api/libraries/demo/apps/team").json()
    assert detail["mas_name"] == "team"

    resp = client.post(
        "/api/libraries/demo/apps",
        json={
            "mas_name": "newmas",
            "mas_yaml": "kind: MAS\nmetadata:\n  name: newmas\n",
            "agents": {"agent1": "kind: Agent\nmetadata:\n  name: agent1\n"},
        },
    )
    assert resp.status_code == 201
    assert (sample_lab / "apps" / "newmas" / "mas.yaml").exists()

    client.delete("/api/libraries/demo/apps/newmas")


def test_pipeline_step_types(client):
    data = client.get("/api/pipeline-step-types").json()
    assert "step_types" in data
    assert len(data["step_types"]) > 0


def test_metrics_endpoints(client):
    assert client.get("/api/metrics/eval").status_code == 200
    assert client.get("/api/metrics/mce").status_code == 200


def test_jobs_list_empty(client):
    from mas.lab.controller import jobs

    jobs._jobs.clear()
    assert client.get("/api/jobs").json()["jobs"] == []


def test_config_files(client):
    data = client.get("/api/libraries/demo/config-files").json()
    assert "infra" in data
