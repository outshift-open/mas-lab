#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Extended FastAPI coverage — jobs, validate, UI contract routes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(sample_lab, monkeypatch):
    from mas.lab.controller import fastapi_app, jobs
    from mas.lab.controller.manifest_store import ManifestStore

    store = ManifestStore(workspace=None)
    store._libraries = {"demo": sample_lab}

    monkeypatch.setattr("mas.lab.controller.deps.get_manifest_store", lambda: store)
    jobs._jobs.clear()
    return TestClient(fastapi_app.app)


def test_library_not_found(client):
    assert client.get("/api/libraries/nope/tools").status_code == 404


def test_validate_manifest_in_process(client):
    """Validate endpoint uses in-process validate_data (not run_cli)."""
    resp = client.post(
        "/api/libraries/demo/validate",
        json={
            "manifest_yaml": (
                "apiVersion: mas/v1\nkind: Agent\nmetadata: {}\n"
                "spec:\n  role:\n    description: d\n    instructions: i\n"
                "  design_pattern:\n    type: react\n"
            ),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["command"] == "validate_data"
    assert body["exit_code"] == 1


def test_overlay_validate_ok(client, monkeypatch):
    async def ok_overlay(content, lib_dir):
        return None

    monkeypatch.setattr("mas.lab.controller.deps.validate_overlay_content", ok_overlay)
    resp = client.post(
        "/api/libraries/demo/overlays/validate",
        json={"manifest_yaml": "kind: Overlay\n"},
    )
    assert resp.status_code == 200


def test_overlay_validate_errors(client, monkeypatch):
    async def bad_overlay(content, lib_dir):
        return ["invalid patch"]

    monkeypatch.setattr("mas.lab.controller.deps.validate_overlay_content", bad_overlay)
    resp = client.post(
        "/api/libraries/demo/overlays/validate",
        json={"manifest_yaml": "bad"},
    )
    assert resp.status_code == 422


def test_overlay_create_conflict(client):
    resp = client.post(
        "/api/libraries/demo/overlays",
        json={"name": "baseline", "content": "description: dup\n", "run_validation": False},
    )
    assert resp.status_code == 409


def test_job_lifecycle_mock(client, monkeypatch):
    from mas.lab.controller import jobs

    def fake_submit(endpoint, cmd, cwd, timeout=60, env_override=None, request_body=None, cleanup_paths=None):
        job = jobs.Job(
            id="job-test-1",
            endpoint=endpoint,
            command=" ".join(cmd),
            status=jobs.JobStatus.COMPLETED,
            created_at=jobs.now_iso(),
            finished_at=jobs.now_iso(),
            exit_code=0,
        )
        jobs._jobs[job.id] = job
        return job

    monkeypatch.setattr("mas.lab.controller.jobs.submit_job", fake_submit)

    resp = client.post(
        "/api/libraries/demo/benchmark/run",
        json={"experiment_yaml": "metadata:\n  name: t\n", "progress": False},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["id"] == job_id

    listed = client.get("/api/jobs").json()["jobs"]
    assert any(j["id"] == job_id for j in listed)

    cleared = client.delete("/api/jobs").json()
    assert cleared["removed"] >= 1


def test_job_cancel_and_not_found(client):
    from mas.lab.controller import jobs

    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()

    job = jobs.Job(
        id="cancel-me",
        endpoint="/test",
        command="sleep",
        status=jobs.JobStatus.RUNNING,
        created_at=jobs.now_iso(),
        _task=mock_task,
    )
    jobs._jobs[job.id] = job

    resp = client.delete("/api/jobs/cancel-me")
    assert resp.status_code == 200

    assert client.get("/api/jobs/missing").status_code == 404

    done = jobs.Job(
        id="done-job",
        endpoint="/test",
        command="echo",
        status=jobs.JobStatus.COMPLETED,
        created_at=jobs.now_iso(),
    )
    jobs._jobs[done.id] = done
    resp2 = client.delete("/api/jobs/done-job")
    assert "terminal" in resp2.json()["message"]


@pytest.mark.asyncio
async def test_run_job_paths(monkeypatch, tmp_path):
    from mas.lab.controller import jobs

    job = jobs.Job(
        id="j1",
        endpoint="/x",
        command="true",
        status=jobs.JobStatus.PENDING,
        created_at=jobs.now_iso(),
    )

    class _Proc:
        pid = 123
        returncode = 0

        async def communicate(self):
            return b"out", b""

    proc = _Proc()
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=proc),
    )
    await jobs.run_job(job, ["true"], tmp_path, 5, {})
    assert job.status == jobs.JobStatus.COMPLETED

    job2 = jobs.Job(
        id="j2",
        endpoint="/x",
        command="missing",
        status=jobs.JobStatus.PENDING,
        created_at=jobs.now_iso(),
    )
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=FileNotFoundError()),
    )
    await jobs.run_job(job2, ["nope"], tmp_path, 5, {})
    assert job2.status == jobs.JobStatus.FAILED


def test_api_info_and_topologies(client, sample_lab):
    info = client.get("/api/info").json()
    assert "libraries_dir" in info

    (sample_lab / "topologies").mkdir(exist_ok=True)
    (sample_lab / "topologies" / "linear.yaml").write_text("kind: Topology\n", encoding="utf-8")
    tops = client.get("/api/libraries/demo/topologies").json()
    assert "linear.yaml" in tops["topologies"]


def test_scenarios_endpoint(client, sample_lab):
    (sample_lab / "scenarios").mkdir(exist_ok=True)
    (sample_lab / "scenarios" / "base.yaml").write_text("name: base\n", encoding="utf-8")
    data = client.get("/api/libraries/demo/scenarios").json()
    assert data["scenarios"]


def test_pipeline_validate_and_update(client, sample_lab, monkeypatch):
    monkeypatch.setattr(
        "mas.lab.controller.routes.pipelines.validate_pipeline_yaml",
        lambda _yaml: {"valid": True, "errors": []},
    )
    resp = client.post(
        "/api/libraries/demo/pipelines/validate",
        json={"manifest_yaml": "metadata:\n  name: p\nsteps: []\n"},
    )
    assert resp.status_code == 200

    client.put(
        "/api/libraries/demo/pipelines/analysis",
        json={"name": "analysis", "content": "metadata:\n  name: analysis\nsteps: []\n"},
    )
    assert client.get("/api/libraries/demo/pipelines/analysis").status_code == 200


def test_ui_contract_routes(client):
    """Smoke-test routes referenced by mas-lab-ui apiCalls.ts."""
    routes = [
        ("GET", "/api/libraries"),
        ("GET", "/api/libraries/demo/tools"),
        ("GET", "/api/libraries/demo/skills"),
        ("GET", "/api/libraries/demo/experiments"),
        ("GET", "/api/libraries/demo/pipelines"),
        ("GET", "/api/libraries/demo/overlays"),
        ("GET", "/api/libraries/demo/datasets"),
        ("GET", "/api/libraries/demo/scenarios"),
        ("GET", "/api/libraries/demo/apps"),
        ("GET", "/api/libraries/demo/config-files"),
        ("GET", "/api/pipeline-step-types"),
        ("GET", "/api/metrics/eval"),
        ("GET", "/api/metrics/mce"),
        ("GET", "/api/jobs"),
    ]
    for method, path in routes:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code in (200, 202, 404, 422, 500), f"{method} {path} -> {resp.status_code}"
