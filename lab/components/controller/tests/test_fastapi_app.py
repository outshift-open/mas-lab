#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for FastAPI app using demo fixture data.

The demo data lives in ``fixtures/demo_lab/`` — a self-contained,
version-controlled lab tree that is copied into ``tmp_path`` for each test
so CRUD operations never mutate the checked-in fixtures.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DEMO_LAB = Path(__file__).resolve().parent / "fixtures" / "demo_lab"
_TEMPLATES = Path(__file__).resolve().parent / "fixtures" / "templates"


def _fake_store(lab: Path):
    from mas.lab.controller.manifest_store import ManifestStore

    store = ManifestStore(workspace=None)
    store._libraries = {"demo": lab}
    return store


@pytest.fixture
def demo_lab(tmp_path: Path) -> Path:
    """Copy the demo_lab fixture tree into a temp directory."""
    dest = tmp_path / "demo_lab"
    shutil.copytree(_DEMO_LAB, dest)
    return dest


@pytest.fixture
def client(demo_lab, monkeypatch):
    from mas.lab.controller import fastapi_app

    monkeypatch.setattr(
        "mas.lab.controller.deps.get_manifest_store",
        lambda: _fake_store(demo_lab),
    )
    return TestClient(fastapi_app.app)


# -- Health -------------------------------------------------------------------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


# -- Libraries ----------------------------------------------------------------

def test_list_libraries(client):
    data = client.get("/api/libraries").json()
    assert len(data["libraries"]) == 1
    assert data["libraries"][0]["dir"] == "demo"


# -- Tools & Skills -----------------------------------------------------------

def test_tools_and_skills(client):
    tools = client.get("/api/libraries/demo/tools").json()["tools"]
    tool_names = {t["name"] for t in tools}
    assert "global/calc" in tool_names
    assert "global/web-search" in tool_names

    skills = client.get("/api/libraries/demo/skills").json()["skills"]
    skill_names = {s["name"] for s in skills}
    assert "global/answer-formatting" in skill_names


# -- Experiments CRUD ---------------------------------------------------------

def test_experiments_crud(client, demo_lab):
    listed = client.get("/api/libraries/demo/experiments").json()["experiments"]
    assert any(e["name"] == "trip-planner-design-pattern-experiment" for e in listed)

    detail = client.get(
        "/api/libraries/demo/experiments/trip-planner-design-pattern-experiment",
    ).json()
    assert "trip-planner-design-pattern-experiment" in detail["content"]

    newone_yaml = (_TEMPLATES / "new-experiment.yaml").read_text(encoding="utf-8")
    resp = client.post(
        "/api/libraries/demo/experiments",
        json={"name": "newone", "content": newone_yaml},
    )
    assert resp.status_code == 201
    assert (demo_lab / "experiments" / "newone.yaml").exists()

    client.put(
        "/api/libraries/demo/experiments/newone",
        json={"name": "renamed", "content": "metadata:\n  name: renamed\n"},
    )
    assert (demo_lab / "experiments" / "renamed.yaml").exists()

    client.delete("/api/libraries/demo/experiments/renamed")
    assert not (demo_lab / "experiments" / "renamed.yaml").exists()


# -- Pipelines & Overlays ----------------------------------------------------

def test_pipelines_and_overlays(client):
    pipes = client.get("/api/libraries/demo/pipelines").json()["pipelines"]
    pipe_names = {p["name"] for p in pipes}
    assert "pipeline-test" in pipe_names

    overlays = client.get("/api/libraries/demo/overlays").json()["overlays"]
    overlay_names = {o["name"] for o in overlays}
    assert "cot-moderator" in overlay_names
    assert "react-moderator" in overlay_names

    detail = client.get("/api/libraries/demo/overlays/cot-moderator").json()
    assert "cot-moderator" in detail["content"]


# -- Datasets -----------------------------------------------------------------

def test_datasets(client):
    datasets = client.get("/api/libraries/demo/datasets").json()["datasets"]
    dataset_names = {d["name"] for d in datasets}
    assert "queries.yaml" in dataset_names
    assert "benchmark.yaml" in dataset_names


# -- MAS Resources (apps) ----------------------------------------------------

def test_mas_resources(client, demo_lab):
    listed = client.get("/api/libraries/demo/apps").json()["mas_resources"]
    assert "trip-planner" in listed

    detail = client.get("/api/libraries/demo/apps/trip-planner").json()
    assert detail["mas_name"] == "trip-planner"

    mas_yaml = (_TEMPLATES / "new-mas.yaml").read_text(encoding="utf-8")
    agents = {
        "coordinator": (_TEMPLATES / "new-mas-coordinator.yaml").read_text(encoding="utf-8"),
        "researcher": (_TEMPLATES / "new-mas-researcher.yaml").read_text(encoding="utf-8"),
    }
    resp = client.post(
        "/api/libraries/demo/apps",
        json={"mas_name": "newmas", "mas_yaml": mas_yaml, "agents": agents},
    )
    assert resp.status_code == 201
    assert (demo_lab / "apps" / "newmas" / "mas.yaml").exists()

    updated_mas_yaml = mas_yaml.replace("name: newmas", "name: renamed-mas")
    resp = client.put(
        "/api/libraries/demo/apps/newmas",
        json={"mas_name": "renamed-mas", "mas_yaml": updated_mas_yaml, "agents": agents},
    )
    assert resp.status_code == 200
    assert (demo_lab / "apps" / "renamed-mas" / "mas.yaml").exists()
    assert not (demo_lab / "apps" / "newmas").exists()

    client.delete("/api/libraries/demo/apps/renamed-mas")


# -- Pipeline step types ------------------------------------------------------

def test_pipeline_step_types(client):
    data = client.get("/api/pipeline-step-types").json()
    assert "step_types" in data
    assert len(data["step_types"]) > 0


# -- Metrics ------------------------------------------------------------------

def test_metrics_endpoints(client):
    assert client.get("/api/metrics/eval").status_code == 200
    assert client.get("/api/metrics/mce").status_code == 200


# -- Jobs ---------------------------------------------------------------------

def test_jobs_list_empty(client):
    from mas.lab.controller import jobs

    jobs._jobs.clear()
    assert client.get("/api/jobs").json()["jobs"] == []


# -- Config files -------------------------------------------------------------

def test_config_files(client):
    data = client.get("/api/libraries/demo/config-files").json()
    assert "infra" in data
    infra_files = data["infra"]
    assert any("tool-providers" in k for k in infra_files)
    assert "flavours" in data
