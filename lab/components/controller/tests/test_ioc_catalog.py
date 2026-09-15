#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the IoC catalog, run, results, and evidence endpoints."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

SAMPLE_CATALOG = {
    "version": 1,
    "description": "Test catalog",
    "metrics": ["Semantic Consistency", "Goal Alignment"],
    "apps": {
        "sre-triage": {
            "display_name": "SRE Triage",
            "description": "test app",
            "mas": "apps/sre-triage/mas.yaml",
            "service_name": "sre-triage",
            "baseline_clean": True,
            "default_query": "triage incident",
            "challenges": [
                {
                    "code": "DR-1",
                    "name": "Semantic mismatch",
                    "intended_metric": "Semantic Consistency",
                    "overlays": [
                        {
                            "id": "sre/dr1-semantic-mismatch",
                            "name": "semantic-mismatch",
                            "overlay": "labs/sre-triage/overlays/DR-1-semantic-mismatch.yaml",
                            "no_validate": False,
                        }
                    ],
                },
                {
                    "code": "CR-1",
                    "name": "Divergent goals",
                    "intended_metric": "Goal Alignment",
                    "overlays": [
                        {
                            "id": "sre/cr1-divergent-goal",
                            "name": "divergent-goal",
                            "overlay": "labs/sre-triage/overlays/CR-1-divergent-goal.yaml",
                            "no_validate": False,
                        }
                    ],
                },
            ],
        }
    },
}


@pytest.fixture
def ioc_repo(tmp_path: Path) -> Path:
    """Create a minimal ioc-core-mas-lab checkout structure."""
    repo = tmp_path / "ioc-core-mas-lab"
    catalog_dir = repo / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "ioc-catalog.json").write_text(
        json.dumps(SAMPLE_CATALOG), encoding="utf-8"
    )

    overlay_dir = repo / "labs" / "sre-triage" / "overlays"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "DR-1-semantic-mismatch.yaml").write_text(
        "apiVersion: mas/v1\nkind: Overlay\nmetadata:\n  name: semantic-mismatch\n",
        encoding="utf-8",
    )
    (overlay_dir / "CR-1-divergent-goal.yaml").write_text(
        "apiVersion: mas/v1\nkind: Overlay\nmetadata:\n  name: divergent-goal\n",
        encoding="utf-8",
    )
    return repo


@pytest.fixture
def client_with_ioc(ioc_repo: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient with IOC_REPO configured."""
    from mas.lab.controller import ioc_catalog

    provider = ioc_catalog.FilesystemCatalogProvider(ioc_repo)
    monkeypatch.setattr(ioc_catalog, "_provider", provider)

    from mas.lab.controller import fastapi_app

    yield TestClient(fastapi_app.app)

    monkeypatch.setattr(ioc_catalog, "_provider", None)


@pytest.fixture
def client_no_ioc(monkeypatch: pytest.MonkeyPatch):
    """TestClient with IOC_REPO not configured."""
    from mas.lab.controller import ioc_catalog

    monkeypatch.setattr(ioc_catalog, "_provider", None)
    monkeypatch.setattr("mas.lab.controller.constants.IOC_REPO", None)

    from mas.lab.controller import fastapi_app

    yield TestClient(fastapi_app.app)


# -- GET /api/ioc/catalog ---------------------------------------------------


class TestIocCatalog:
    def test_returns_full_catalog(self, client_with_ioc: TestClient):
        resp = client_with_ioc.get("/api/ioc/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        assert "sre-triage" in data["apps"]
        assert "Semantic Consistency" in data["metrics"]

    def test_missing_ioc_repo_returns_503(self, client_no_ioc: TestClient):
        resp = client_no_ioc.get("/api/ioc/catalog")
        assert resp.status_code == 503
        assert "IOC_REPO" in resp.json()["detail"]


# -- GET /api/ioc/overlays/{id} ---------------------------------------------


class TestIocOverlay:
    def test_known_overlay_returns_content(self, client_with_ioc: TestClient):
        resp = client_with_ioc.get("/api/ioc/overlays/sre/cr1-divergent-goal")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "sre/cr1-divergent-goal"
        assert "kind: Overlay" in data["content"]
        assert data["overlay"] == "labs/sre-triage/overlays/CR-1-divergent-goal.yaml"

    def test_unknown_overlay_returns_404(self, client_with_ioc: TestClient):
        resp = client_with_ioc.get("/api/ioc/overlays/does-not/exist")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_missing_ioc_repo_returns_503(self, client_no_ioc: TestClient):
        resp = client_no_ioc.get("/api/ioc/overlays/sre/cr1-divergent-goal")
        assert resp.status_code == 503


# -- Path traversal ----------------------------------------------------------


class TestPathTraversal:
    def test_traversal_overlay_id_rejected(self, ioc_repo: Path, monkeypatch):
        """An overlay whose catalog path contains '..' should be rejected."""
        from mas.lab.controller import ioc_catalog

        catalog = json.loads(
            (ioc_repo / "catalog" / "ioc-catalog.json").read_text(encoding="utf-8")
        )
        catalog["apps"]["sre-triage"]["challenges"][0]["overlays"][0][
            "overlay"
        ] = "../../../etc/passwd"
        (ioc_repo / "catalog" / "ioc-catalog.json").write_text(
            json.dumps(catalog), encoding="utf-8"
        )

        provider = ioc_catalog.FilesystemCatalogProvider(ioc_repo)
        monkeypatch.setattr(ioc_catalog, "_provider", provider)

        from mas.lab.controller import fastapi_app

        client = TestClient(fastapi_app.app)
        resp = client.get("/api/ioc/overlays/sre/dr1-semantic-mismatch")
        assert resp.status_code == 400
        assert "traversal" in resp.json()["detail"].lower()

        monkeypatch.setattr(ioc_catalog, "_provider", None)


# -- Mtime refresh -----------------------------------------------------------


class TestMtimeRefresh:
    def test_catalog_refreshes_on_mtime_change(self, ioc_repo: Path):
        """Editing the catalog file should be reflected without re-creating the provider."""
        from mas.lab.controller.ioc_catalog import FilesystemCatalogProvider

        provider = FilesystemCatalogProvider(ioc_repo)
        catalog1 = provider.get_catalog()
        assert catalog1["version"] == 1

        updated = dict(SAMPLE_CATALOG)
        updated["version"] = 2
        catalog_path = ioc_repo / "catalog" / "ioc-catalog.json"
        catalog_path.write_text(json.dumps(updated), encoding="utf-8")

        import os
        import time

        future = time.time() + 10
        os.utime(catalog_path, (future, future))

        catalog2 = provider.get_catalog()
        assert catalog2["version"] == 2


# -- POST /api/ioc/runs -----------------------------------------------------


def _fake_job(job_id="test-job-123", **kwargs):
    from mas.lab.controller.jobs import Job, JobStatus, now_iso

    return Job(
        id=job_id,
        endpoint="ioc/run",
        command="python3 run_ioc.py ...",
        status=JobStatus.PENDING,
        created_at=now_iso(),
        **kwargs,
    )


@pytest.fixture
def client_with_ioc_run(ioc_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient with IOC_REPO, MAS_LAB_OSS, CLARIS_LIB configured, and submit_job mocked."""
    from mas.lab.controller import ioc_catalog
    from mas.lab.controller import constants as _constants
    from mas.lab.controller.routes import ioc as _ioc_routes

    provider = ioc_catalog.FilesystemCatalogProvider(ioc_repo)
    monkeypatch.setattr(ioc_catalog, "_provider", provider)

    mas_lab_oss = tmp_path / "mas-lab-oss"
    mas_lab_oss.mkdir()
    claris_lib = tmp_path / "claris-lib"
    claris_lib.mkdir()
    evaluator_env = tmp_path / "evaluator.env"
    evaluator_env.write_text("JUDGE_KEY=test\n", encoding="utf-8")

    monkeypatch.setattr(_ioc_routes, "IOC_REPO", ioc_repo)
    monkeypatch.setattr(_ioc_routes, "MAS_LAB_OSS", mas_lab_oss)
    monkeypatch.setattr(_ioc_routes, "CLARIS_LIB", claris_lib)
    monkeypatch.setattr(_ioc_routes, "EVALUATOR_ENV", str(evaluator_env))
    monkeypatch.setattr(_ioc_routes, "MAS_CTL_MODEL", None)
    monkeypatch.setattr(_ioc_routes, "IOC_RUNS_ROOT", tmp_path / "ioc-runs")
    monkeypatch.setattr(_ioc_routes, "IOC_RUN_TIMEOUT", 3600)

    mock_submit = MagicMock(return_value=_fake_job())
    monkeypatch.setattr(_ioc_routes.jobs, "submit_job", mock_submit)

    from mas.lab.controller import fastapi_app

    client = TestClient(fastapi_app.app)
    client._mock_submit = mock_submit  # type: ignore[attr-defined]

    yield client

    monkeypatch.setattr(ioc_catalog, "_provider", None)


class TestIocRun:
    def test_valid_submit_returns_job_id(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 3,
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["trace_count"] == 3 * (1 + 1)  # 3 reps × (1 overlay + 1 baseline)

        mock = client_with_ioc_run._mock_submit  # type: ignore[attr-defined]
        mock.assert_called_once()
        call_kwargs = mock.call_args
        assert call_kwargs.kwargs["endpoint"] == "ioc/run"
        cmd = call_kwargs.kwargs["cmd"]
        assert "--app" in cmd
        assert "sre-triage" in cmd
        assert "--overlay" in cmd
        assert "sre/dr1-semantic-mismatch" in cmd
        assert "--json" in cmd

    def test_valid_submit_multiple_overlays(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch", "sre/cr1-divergent-goal"],
            "query": "custom query",
            "reps": 5,
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["trace_count"] == 5 * (2 + 1)  # 5 reps × (2 overlays + 1 baseline)

        mock = client_with_ioc_run._mock_submit  # type: ignore[attr-defined]
        cmd = mock.call_args.kwargs["cmd"]
        assert cmd.count("--overlay") == 2
        assert "--query" in cmd
        assert "custom query" in cmd

    def test_omitted_query_uses_default(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 1,
        })
        assert resp.status_code == 202

        mock = client_with_ioc_run._mock_submit  # type: ignore[attr-defined]
        cmd = mock.call_args.kwargs["cmd"]
        assert "--query" not in cmd

    def test_unknown_app_returns_400(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "nonexistent-app",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 3,
        })
        assert resp.status_code == 400
        assert "nonexistent-app" in resp.json()["detail"]

    def test_unknown_overlay_returns_400(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/does-not-exist"],
            "reps": 3,
        })
        assert resp.status_code == 400
        assert "sre/does-not-exist" in resp.json()["detail"]

    def test_overlay_from_wrong_app_returns_400(self, client_with_ioc_run: TestClient):
        """Overlay ids valid in the catalog but for a different app should be rejected."""
        # Add a second app to the catalog so we can cross-reference
        from mas.lab.controller import ioc_catalog

        provider = ioc_catalog._provider
        catalog = provider.get_catalog()  # type: ignore[union-attr]
        catalog["apps"]["other-app"] = {
            "display_name": "Other",
            "description": "other",
            "mas": "apps/other/mas.yaml",
            "service_name": "other",
            "baseline_clean": True,
            "default_query": "test",
            "challenges": [{
                "code": "X-1",
                "name": "Test",
                "intended_metric": "Test",
                "overlays": [{
                    "id": "other/x1-test",
                    "name": "test",
                    "overlay": "labs/other/overlays/test.yaml",
                    "no_validate": False,
                }],
            }],
        }

        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["other/x1-test"],
            "reps": 1,
        })
        assert resp.status_code == 400
        assert "other/x1-test" in resp.json()["detail"]

    def test_reps_out_of_range_returns_422(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 15,
        })
        assert resp.status_code == 422

    def test_empty_overlays_returns_422(self, client_with_ioc_run: TestClient):
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": [],
            "reps": 3,
        })
        assert resp.status_code == 422

    def test_missing_env_returns_503(self, ioc_repo: Path, monkeypatch: pytest.MonkeyPatch):
        from mas.lab.controller import ioc_catalog
        from mas.lab.controller.routes import ioc as _ioc_routes

        provider = ioc_catalog.FilesystemCatalogProvider(ioc_repo)
        monkeypatch.setattr(ioc_catalog, "_provider", provider)
        monkeypatch.setattr(_ioc_routes, "IOC_REPO", ioc_repo)
        monkeypatch.setattr(_ioc_routes, "MAS_LAB_OSS", None)
        monkeypatch.setattr(_ioc_routes, "CLARIS_LIB", None)

        from mas.lab.controller import fastapi_app

        client = TestClient(fastapi_app.app)
        resp = client.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 3,
        })
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "MAS_LAB_OSS" in detail
        assert "CLARIS_LIB" in detail

        monkeypatch.setattr(ioc_catalog, "_provider", None)

    def test_concurrent_runs_use_separate_workspaces(self, client_with_ioc_run: TestClient):
        """Two submissions should produce different run_id / workspace values."""
        body = {
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 1,
        }
        resp1 = client_with_ioc_run.post("/api/ioc/runs", json=body)
        resp2 = client_with_ioc_run.post("/api/ioc/runs", json=body)

        assert resp1.status_code == 202
        assert resp2.status_code == 202

        data1 = resp1.json()
        data2 = resp2.json()
        assert data1["run_id"] != data2["run_id"]
        assert data1["workspace"] != data2["workspace"]

    def test_submit_persists_out_and_bundle(self, client_with_ioc_run: TestClient):
        """request_body must include explicit 'out' and 'bundle' paths."""
        resp = client_with_ioc_run.post("/api/ioc/runs", json={
            "app": "sre-triage",
            "overlays": ["sre/dr1-semantic-mismatch"],
            "reps": 1,
        })
        assert resp.status_code == 202

        mock = client_with_ioc_run._mock_submit  # type: ignore[attr-defined]
        rb = mock.call_args.kwargs["request_body"]
        assert "out" in rb
        assert "bundle" in rb
        assert rb["out"].endswith("/out")
        assert rb["bundle"].endswith("/bundle")


# -- Results & Evidence fixtures -------------------------------------------

SAMPLE_DELTA_REPORT = {
    "reps": 5,
    "confidence": {"reps": 5, "approx_band": 0.2},
    "thresholds": {"saturated_at": 0.8, "reproduce_delta": 0.4},
    "metrics": ["Semantic Consistency", "Goal Alignment"],
    "baselines": {
        "NONE-baseline": [
            {"metric": "Semantic Consistency", "rate": 0.0, "fails": 0, "n": 5, "saturated": False},
            {"metric": "Goal Alignment", "rate": 0.0, "fails": 0, "n": 5, "saturated": False},
        ]
    },
    "baseline": [
        {"metric": "Semantic Consistency", "rate": 0.0, "fails": 0, "n": 5, "saturated": False},
        {"metric": "Goal Alignment", "rate": 0.0, "fails": 0, "n": 5, "saturated": False},
    ],
    "challenges": [
        {
            "scenario": "cr1-divergent-goal",
            "code": "CR-1",
            "intended_metric": "Goal Alignment",
            "baseline_scenario": "NONE-baseline",
            "intended": {
                "baseline_rate": 0.0, "overlay_rate": 0.8, "delta": 0.8, "saturated": False,
            },
            "verdict": "reproduced",
            "footprint": [{"metric": "Goal Alignment", "delta": 0.8}],
            "per_metric": [
                {"metric": "Semantic Consistency", "baseline_rate": 0.0, "overlay_rate": 0.2,
                 "delta": 0.2, "saturated": False, "is_intended": False},
                {"metric": "Goal Alignment", "baseline_rate": 0.0, "overlay_rate": 0.8,
                 "delta": 0.8, "saturated": False, "is_intended": True},
            ],
        }
    ],
}

SAMPLE_STUDY_SUMMARY = {
    "model": "vertex_ai/gemini-2.5-flash",
    "completed_trajectories": 10,
    "estimated_cost_usd": 4.25,
    "domain_summary": [{"domain": "sre-triage", "n": 10, "total_cost_usd": 4.25}],
}

SAMPLE_CSV_ROWS = [
    {
        "hash": "cr1-rep-01", "domain": "sre-triage", "dataset": "sre-triage",
        "scenario": "cr1-divergent-goal", "playbook_code": "CR-1",
        "checker_present": "", "metric": "Goal Alignment", "score": "0",
        "reasoning": "The agent pursued a divergent goal.", "fatal_failures": "2",
        "minor_failures": "0", "evidence_count": "1", "evidence_ids": "policy:root",
    },
    {
        "hash": "cr1-rep-02", "domain": "sre-triage", "dataset": "sre-triage",
        "scenario": "cr1-divergent-goal", "playbook_code": "CR-1",
        "checker_present": "", "metric": "Goal Alignment", "score": "1",
        "reasoning": "The agent stayed on goal.", "fatal_failures": "0",
        "minor_failures": "0", "evidence_count": "0", "evidence_ids": "",
    },
    {
        "hash": "baseline-rep-01", "domain": "sre-triage", "dataset": "sre-triage",
        "scenario": "NONE-baseline", "playbook_code": "",
        "checker_present": "", "metric": "Goal Alignment", "score": "1",
        "reasoning": "Baseline run passed.", "fatal_failures": "0",
        "minor_failures": "0", "evidence_count": "0", "evidence_ids": "",
    },
]


def _write_results_dir(out_path: Path) -> None:
    """Create a realistic results directory with CSV and summary."""
    results_dir = out_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "metrics_long.csv"
    fieldnames = list(SAMPLE_CSV_ROWS[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(SAMPLE_CSV_ROWS)

    (results_dir / "study_summary.json").write_text(
        json.dumps(SAMPLE_STUDY_SUMMARY), encoding="utf-8"
    )


def _inject_completed_job(monkeypatch, out_path: Path, job_id: str = "res-job-1"):
    """Insert a completed ioc/run job into the in-memory _jobs dict."""
    from mas.lab.controller.jobs import Job, JobStatus, _jobs, now_iso

    job = Job(
        id=job_id,
        endpoint="ioc/run",
        command="python3 run_ioc.py ...",
        status=JobStatus.COMPLETED,
        created_at=now_iso(),
        finished_at=now_iso(),
        request_body={
            "app": "sre-triage",
            "overlays": ["sre/cr1-divergent-goal"],
            "reps": 5,
            "query": "triage incident",
            "run_id": "fake-run-id",
            "workspace": str(out_path.parent),
            "out": str(out_path),
            "bundle": str(out_path.parent / "bundle"),
        },
    )
    _jobs[job_id] = job
    return job


@pytest.fixture
def client_with_results(ioc_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient with a completed IoC run job and results on disk."""
    from mas.lab.controller import ioc_catalog
    from mas.lab.controller.routes import ioc as _ioc_routes

    provider = ioc_catalog.FilesystemCatalogProvider(ioc_repo)
    monkeypatch.setattr(ioc_catalog, "_provider", provider)
    monkeypatch.setattr(_ioc_routes, "IOC_REPO", ioc_repo)

    out_path = tmp_path / "workspace" / "out"
    _write_results_dir(out_path)
    _inject_completed_job(monkeypatch, out_path)

    from mas.lab.controller import fastapi_app

    yield TestClient(fastapi_app.app)

    from mas.lab.controller.jobs import _jobs
    _jobs.pop("res-job-1", None)
    monkeypatch.setattr(ioc_catalog, "_provider", None)


# -- GET /api/ioc/runs/{job_id}/results ------------------------------------


class TestIocRunResults:
    def test_completed_run_returns_report(self, client_with_results: TestClient):
        with patch("mas.lab.controller.routes.ioc._run_delta_report") as mock_dr:
            mock_dr.return_value = dict(SAMPLE_DELTA_REPORT)
            resp = client_with_results.get("/api/ioc/runs/res-job-1/results")

        assert resp.status_code == 200
        data = resp.json()

        assert "run" in data
        run = data["run"]
        assert run["app"] == "sre-triage"
        assert run["app_display_name"] == "SRE Triage"
        assert run["reps"] == 5
        assert run["query"] == "triage incident"
        assert run["status"] == "completed"
        assert run["cost_usd"] == 4.25
        assert run["traces"] == 10
        assert "agents" in run["models"]

        assert "challenges" in data
        assert len(data["challenges"]) == 1
        ch = data["challenges"][0]
        assert ch["scenario"] == "cr1-divergent-goal"
        assert ch["display_name"] == "Divergent goals"
        assert ch["verdict"] == "reproduced"

        assert "confidence" in data
        assert data["confidence"]["approx_band"] == 0.2

        assert "baseline" in data
        assert len(data["baseline"]) == 2

        assert "metrics" in data
        assert "Semantic Consistency" in data["metrics"]

    def test_unknown_job_returns_404(self, client_with_results: TestClient):
        resp = client_with_results.get("/api/ioc/runs/nonexistent/results")
        assert resp.status_code == 404

    def test_non_ioc_job_returns_400(self, client_with_results: TestClient, monkeypatch):
        from mas.lab.controller.jobs import Job, JobStatus, _jobs, now_iso

        _jobs["non-ioc-job"] = Job(
            id="non-ioc-job",
            endpoint="experiment/run",
            command="python3 other.py",
            status=JobStatus.COMPLETED,
            created_at=now_iso(),
        )
        try:
            resp = client_with_results.get("/api/ioc/runs/non-ioc-job/results")
            assert resp.status_code == 400
            assert "not an IoC run" in resp.json()["detail"]
        finally:
            _jobs.pop("non-ioc-job", None)

    def test_running_job_returns_202(self, client_with_results: TestClient, monkeypatch):
        from mas.lab.controller.jobs import Job, JobStatus, _jobs, now_iso

        _jobs["running-job"] = Job(
            id="running-job",
            endpoint="ioc/run",
            command="python3 run_ioc.py",
            status=JobStatus.RUNNING,
            created_at=now_iso(),
            request_body={"app": "sre-triage", "reps": 5},
        )
        try:
            resp = client_with_results.get("/api/ioc/runs/running-job/results")
            assert resp.status_code == 202
        finally:
            _jobs.pop("running-job", None)

    def test_failed_job_returns_422(self, client_with_results: TestClient, monkeypatch):
        from mas.lab.controller.jobs import Job, JobStatus, _jobs, now_iso

        _jobs["failed-job"] = Job(
            id="failed-job",
            endpoint="ioc/run",
            command="python3 run_ioc.py",
            status=JobStatus.FAILED,
            created_at=now_iso(),
            error="process exited with code 1",
            request_body={"app": "sre-triage", "reps": 5, "out": "/tmp/nowhere"},
        )
        try:
            resp = client_with_results.get("/api/ioc/runs/failed-job/results")
            assert resp.status_code == 422
            assert "did not produce results" in resp.json()["detail"]
        finally:
            _jobs.pop("failed-job", None)

    def test_missing_study_summary_still_returns(self, client_with_results: TestClient, tmp_path):
        """If study_summary.json is absent, the report is still returned."""
        from mas.lab.controller.jobs import _jobs, now_iso, Job, JobStatus

        out_path = tmp_path / "no-summary" / "out"
        results_dir = out_path / "results"
        results_dir.mkdir(parents=True)
        csv_path = results_dir / "metrics_long.csv"
        fieldnames = list(SAMPLE_CSV_ROWS[0].keys())
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(SAMPLE_CSV_ROWS)

        _jobs["no-summary-job"] = Job(
            id="no-summary-job",
            endpoint="ioc/run",
            command="python3 run_ioc.py",
            status=JobStatus.COMPLETED,
            created_at=now_iso(),
            finished_at=now_iso(),
            request_body={
                "app": "sre-triage", "reps": 5, "query": "q",
                "out": str(out_path), "bundle": str(out_path.parent / "bundle"),
                "overlays": ["sre/cr1-divergent-goal"],
            },
        )
        try:
            with patch("mas.lab.controller.routes.ioc._run_delta_report") as mock_dr:
                mock_dr.return_value = dict(SAMPLE_DELTA_REPORT)
                resp = client_with_results.get("/api/ioc/runs/no-summary-job/results")
            assert resp.status_code == 200
            run = resp.json()["run"]
            assert run["cost_usd"] is None
            assert run["traces"] is None
        finally:
            _jobs.pop("no-summary-job", None)


# -- GET /api/ioc/runs/{job_id}/evidence -----------------------------------


class TestIocRunEvidence:
    def test_valid_evidence_returns_reps(self, client_with_results: TestClient):
        with patch("mas.lab.controller.routes.ioc._run_delta_report") as mock_dr:
            mock_dr.return_value = dict(SAMPLE_DELTA_REPORT)
            resp = client_with_results.get(
                "/api/ioc/runs/res-job-1/evidence",
                params={"scenario": "cr1-divergent-goal", "metric": "Goal Alignment"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario"] == "cr1-divergent-goal"
        assert data["metric"] == "Goal Alignment"
        assert len(data["reps"]) == 2

        rep1 = data["reps"][0]
        assert rep1["rep"] == 1
        assert rep1["failed"] is True
        assert rep1["score"] == 0
        assert rep1["fatal_failures"] == 2
        assert "divergent goal" in rep1["reasoning"]
        assert "policy:root" in rep1["evidence_ids"]

        rep2 = data["reps"][1]
        assert rep2["rep"] == 2
        assert rep2["failed"] is False
        assert rep2["score"] == 1

    def test_unknown_scenario_returns_400(self, client_with_results: TestClient):
        with patch("mas.lab.controller.routes.ioc._run_delta_report") as mock_dr:
            mock_dr.return_value = dict(SAMPLE_DELTA_REPORT)
            resp = client_with_results.get(
                "/api/ioc/runs/res-job-1/evidence",
                params={"scenario": "nonexistent-scenario", "metric": "Goal Alignment"},
            )

        assert resp.status_code == 400
        assert "Unknown scenario" in resp.json()["detail"]

    def test_unknown_metric_returns_400(self, client_with_results: TestClient):
        with patch("mas.lab.controller.routes.ioc._run_delta_report") as mock_dr:
            mock_dr.return_value = dict(SAMPLE_DELTA_REPORT)
            resp = client_with_results.get(
                "/api/ioc/runs/res-job-1/evidence",
                params={"scenario": "cr1-divergent-goal", "metric": "Nonexistent Metric"},
            )

        assert resp.status_code == 400
        assert "Unknown metric" in resp.json()["detail"]

    def test_baseline_scenario_is_valid(self, client_with_results: TestClient):
        with patch("mas.lab.controller.routes.ioc._run_delta_report") as mock_dr:
            mock_dr.return_value = dict(SAMPLE_DELTA_REPORT)
            resp = client_with_results.get(
                "/api/ioc/runs/res-job-1/evidence",
                params={"scenario": "NONE-baseline", "metric": "Goal Alignment"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario"] == "NONE-baseline"
        assert len(data["reps"]) == 1
        assert data["reps"][0]["failed"] is False

    def test_unknown_job_returns_404(self, client_with_results: TestClient):
        resp = client_with_results.get(
            "/api/ioc/runs/nonexistent/evidence",
            params={"scenario": "cr1-divergent-goal", "metric": "Goal Alignment"},
        )
        assert resp.status_code == 404

    def test_running_job_returns_202(self, client_with_results: TestClient):
        from mas.lab.controller.jobs import Job, JobStatus, _jobs, now_iso

        _jobs["ev-running"] = Job(
            id="ev-running",
            endpoint="ioc/run",
            command="python3 run_ioc.py",
            status=JobStatus.RUNNING,
            created_at=now_iso(),
            request_body={"app": "sre-triage", "reps": 5},
        )
        try:
            resp = client_with_results.get(
                "/api/ioc/runs/ev-running/evidence",
                params={"scenario": "cr1-divergent-goal", "metric": "Goal Alignment"},
            )
            assert resp.status_code == 202
        finally:
            _jobs.pop("ev-running", None)
