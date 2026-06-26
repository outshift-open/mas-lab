#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Contract tests mirroring mas-lab-ui ``apiCalls.ts`` HTTP surface."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(sample_lab, monkeypatch):
    from mas.lab.controller import deps, fastapi_app, jobs
    from mas.lab.controller.manifest_store import ManifestStore

    store = ManifestStore(workspace=None)
    store._libraries = {"demo": sample_lab}
    store._registry._libraries = {"demo": sample_lab}

    monkeypatch.setattr(deps, "_manifest_store", None)
    monkeypatch.setattr("mas.lab.controller.deps.get_manifest_store", lambda: store)
    monkeypatch.setattr(
        "mas.lab.controller.lab_registry.LabRegistry.discover_bundled_infra",
        classmethod(lambda cls: {}),
    )
    monkeypatch.setattr(
        "mas.lab.controller.lab_registry.LabRegistry.discover_workspace_infra",
        classmethod(lambda cls, _ws: {}),
    )
    jobs._jobs.clear()
    return TestClient(fastapi_app.app)


@pytest.fixture
def mock_cli(monkeypatch):
    async def fake_cli(cmd, cwd, timeout=60, env_override=None):
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "command": " ".join(cmd)}

    monkeypatch.setattr("mas.lab.controller.deps.run_cli", fake_cli)
    return fake_cli


@pytest.fixture
def mock_submit_job(monkeypatch):
    from mas.lab.controller import jobs

    def fake_submit(endpoint, cmd, cwd, timeout=60, env_override=None, request_body=None, cleanup_paths=None):
        job = jobs.Job(
            id="job-contract-1",
            endpoint=endpoint,
            command=" ".join(cmd),
            status=jobs.JobStatus.COMPLETED,
            created_at=jobs.now_iso(),
            finished_at=jobs.now_iso(),
            exit_code=0,
            stdout="job output",
        )
        jobs._jobs[job.id] = job
        return job

    def fake_chat_submit(
        endpoint,
        manifest_yaml,
        query,
        lib_dir,
        flavour=None,
        session_id=None,
        timeout=60,
        request_body=None,
    ):
        job = jobs.Job(
            id="job-chat-contract-1",
            endpoint=endpoint,
            command=f"agent-chat({lib_dir.name})",
            status=jobs.JobStatus.COMPLETED,
            created_at=jobs.now_iso(),
            finished_at=jobs.now_iso(),
            exit_code=0,
            response="Hello from agent",
            session_id=session_id or "ui:test",
        )
        jobs._jobs[job.id] = job
        return job

    monkeypatch.setattr("mas.lab.controller.jobs.submit_job", fake_submit)
    monkeypatch.setattr("mas.lab.controller.jobs.submit_agent_chat_job", fake_chat_submit)
    return fake_submit


@pytest.fixture
def mock_overlay_validate(monkeypatch):
    monkeypatch.setattr(
        "mas.lab.controller.deps.validate_overlay_content",
        AsyncMock(return_value=None),
    )


@pytest.fixture
def mock_pipeline_validate(monkeypatch):
    monkeypatch.setattr(
        "mas.lab.controller.routes.pipelines.validate_pipeline_yaml",
        lambda _yaml: {"valid": True, "errors": []},
    )


# --- Libraries (apiCalls: fetchLibraries, tools, skills, config-files) ---


def test_contract_libraries_list(client):
    data = client.get("/api/libraries").json()
    assert "libraries" in data
    assert data["libraries"][0]["dir"] == "demo"


def test_contract_tools_skills_config(client):
    tools = client.get("/api/libraries/demo/tools").json()
    assert "tools" in tools
    skills = client.get("/api/libraries/demo/skills").json()
    assert "skills" in skills
    cfg = client.get("/api/libraries/demo/config-files").json()
    assert isinstance(cfg, dict)


# --- Validate (apiCalls: validateManifest) ---


def test_contract_validate_manifest(client, mock_cli):
    resp = client.post(
        "/api/libraries/demo/validate",
        json={"manifest_yaml": "kind: Agent\nmetadata:\n  name: a\n"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "exit_code" in body
    assert "stdout" in body


# --- Jobs (apiCalls: fetchJobs, fetchJobDetail, pollJob) ---


def test_contract_schemas_api(client):
    """apiCalls may migrate to GET /api/schemas/* instead of bundled copies."""
    listed = client.get("/api/schemas").json()
    assert "schemas" in listed
    ids = {s["id"] for s in listed["schemas"]}
    assert {"agent", "mas", "pipeline", "overlay", "infra"}.issubset(ids)

    agent = client.get("/api/schemas/agent")
    assert agent.status_code == 200
    assert "agent" in agent.text.lower() or "Agent" in agent.text


def test_contract_health(client):
    """OSS adds /api/health (UI may probe it for daemon readiness)."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"


def test_contract_jobs(mock_submit_job, client):
    submit = client.post(
        "/api/libraries/demo/benchmark/run",
        json={"experiment_yaml": "metadata:\n  name: t\n", "progress": False},
    )
    assert submit.status_code == 202
    job_id = submit.json()["job_id"]

    listed = client.get("/api/jobs").json()
    assert any(j["id"] == job_id for j in listed["jobs"])

    # apiCalls: fetchJobs(status?) — optional status query param
    filtered = client.get("/api/jobs", params={"status": "completed"}).json()
    assert all(j["status"] == "completed" for j in filtered["jobs"])

    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["id"] == job_id
    assert "stdout" in detail


# --- Run agent / MAS (apiCalls: runAgent, runMas) ---


def test_contract_run_agent_and_mas(mock_submit_job, client):
    agent = client.post(
        "/api/libraries/demo/run",
        json={"manifest_yaml": "kind: Agent\n", "query": "hi", "verbose": False},
    )
    assert agent.status_code == 202
    body = agent.json()
    assert "job_id" in body
    assert "session_id" in body

    mas = client.post(
        "/api/libraries/demo/run-mas",
        json={"manifest_yaml": "kind: MAS\n", "query": "hi", "overlays": []},
    )
    assert mas.status_code == 202
    assert "job_id" in mas.json()


# --- Benchmark (apiCalls: runBenchmark) ---


def test_contract_benchmark_run(mock_submit_job, client):
    resp = client.post(
        "/api/libraries/demo/benchmark/run",
        json={"experiment_yaml": "metadata:\n  name: smoke\n", "progress": True},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"]
    assert body["status"]

    # apiCalls sends max_runs; accept legacy n_runs alias too
    with_runs = client.post(
        "/api/libraries/demo/benchmark/run",
        json={
            "experiment_yaml": "metadata:\n  name: smoke\n",
            "n_runs": 3,
        },
    )
    assert with_runs.status_code == 202
    assert "--max-runs 3" in with_runs.json()["command"]


# --- MAS resources CRUD (apiCalls: fetch/create/update/deleteMasResource) ---


def test_contract_mas_resources_crud(client, sample_lab):
    listed = client.get("/api/libraries/demo/apps").json()
    assert "mas_resources" in listed
    assert "team" in listed["mas_resources"]

    detail = client.get("/api/libraries/demo/apps/team").json()
    assert detail["mas_name"] == "team"

    created = client.post(
        "/api/libraries/demo/apps",
        json={
            "mas_name": "contract-mas",
            "mas_yaml": "kind: MAS\nmetadata:\n  name: contract-mas\n",
            "agents": {},
        },
    )
    assert created.status_code == 201

    updated = client.put(
        "/api/libraries/demo/apps/contract-mas",
        json={
            "mas_name": "contract-mas-renamed",
            "mas_yaml": "kind: MAS\nmetadata:\n  name: contract-mas-renamed\n",
            "agents": {},
        },
    )
    assert updated.status_code == 200

    deleted = client.delete("/api/libraries/demo/apps/contract-mas-renamed")
    assert deleted.status_code in (200, 204)


# --- Scenarios / datasets list (apiCalls: fetchScenarios, fetchDatasets) ---


def test_contract_scenarios_and_datasets(client, sample_lab):
    (sample_lab / "scenarios").mkdir(exist_ok=True)
    (sample_lab / "scenarios" / "base.yaml").write_text("name: base\n", encoding="utf-8")

    scenarios = client.get("/api/libraries/demo/scenarios").json()
    assert "scenarios" in scenarios

    datasets = client.get("/api/libraries/demo/datasets").json()
    assert "datasets" in datasets


# --- Experiments CRUD (apiCalls: fetch/create/update/delete experiment) ---


def test_contract_experiments_crud(client, sample_lab):
    listed = client.get("/api/libraries/demo/experiments").json()
    assert "experiments" in listed

    content = client.get("/api/libraries/demo/experiments/smoke").json()
    assert "content" in content

    created = client.post(
        "/api/libraries/demo/experiments",
        json={"name": "contract-exp", "content": "metadata:\n  name: contract-exp\n"},
    )
    assert created.status_code == 201

    updated = client.put(
        "/api/libraries/demo/experiments/contract-exp",
        json={"name": "contract-exp2", "content": "metadata:\n  name: contract-exp2\n"},
    )
    assert updated.status_code == 200

    deleted = client.delete("/api/libraries/demo/experiments/contract-exp2")
    assert deleted.status_code in (200, 204)


# --- Experiment cache / detail (apiCalls: deleteExperimentCache, fetchExperimentDetail) ---


def test_contract_experiment_cache_and_detail(client, tmp_path, monkeypatch):
    lab_root = tmp_path / "mas-lab-root"
    exp_dir = lab_root / "labs" / "cached-exp"
    exp_dir.mkdir(parents=True)
    (exp_dir / "metadata.yaml").write_text("name: cached-exp\nstatus: done\n", encoding="utf-8")
    (exp_dir / "results.txt").write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr("mas.lab.controller.routes.benchmark.MAS_LAB_ROOT", lab_root)

    listed = client.get("/api/experiments").json()
    assert any(e["name"] == "cached-exp" for e in listed["experiments"])

    detail = client.get("/api/experiments/cached-exp")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "cached-exp"
    assert "tree" in body

    file_resp = client.get("/api/experiments/cached-exp/file", params={"path": "results.txt"})
    assert file_resp.status_code == 200
    assert "content" in file_resp.json()

    cache_del = client.delete("/api/experiments/cached-exp")
    assert cache_del.status_code == 200
    assert not exp_dir.exists()


# --- Pipeline step types (apiCalls: fetchPipelineStepTypes) ---


def test_contract_pipeline_step_types(client):
    data = client.get("/api/pipeline-step-types").json()
    assert "step_types" in data
    assert "categories" in data


# --- Pipelines CRUD + validate + run (apiCalls) ---


def test_contract_pipelines(mock_pipeline_validate, mock_submit_job, client, sample_lab):
    listed = client.get("/api/libraries/demo/pipelines").json()
    assert "pipelines" in listed

    detail = client.get("/api/libraries/demo/pipelines/analysis").json()
    assert "content" in detail

    validate = client.post(
        "/api/libraries/demo/pipelines/validate",
        json={"manifest_yaml": "metadata:\n  name: p\nsteps: []\n"},
    )
    assert validate.status_code == 200

    created = client.post(
        "/api/libraries/demo/pipelines",
        json={"name": "contract-pipe", "content": "metadata:\n  name: contract-pipe\nsteps: []\n"},
    )
    assert created.status_code == 201

    updated = client.put(
        "/api/libraries/demo/pipelines/contract-pipe",
        json={"name": "contract-pipe", "content": "metadata:\n  name: contract-pipe\nsteps: []\n"},
    )
    assert updated.status_code == 200

    run = client.post(
        "/api/libraries/demo/pipeline/run",
        json={"pipeline_yaml": "metadata:\n  name: contract-pipe\nsteps: []\n"},
    )
    assert run.status_code == 202
    assert "job_id" in run.json()

    deleted = client.delete("/api/libraries/demo/pipelines/contract-pipe")
    assert deleted.status_code in (200, 204)


# --- Overlays CRUD + validate (apiCalls) ---


def test_contract_overlays(mock_overlay_validate, client, sample_lab):
    listed = client.get("/api/libraries/demo/overlays").json()
    assert "overlays" in listed

    detail = client.get("/api/libraries/demo/overlays/baseline").json()
    assert "content" in detail

    validate = client.post(
        "/api/libraries/demo/overlays/validate",
        json={"manifest_yaml": "kind: Overlay\n"},
    )
    assert validate.status_code == 200

    created = client.post(
        "/api/libraries/demo/overlays",
        json={"name": "contract-overlay", "content": "description: test\n", "run_validation": False},
    )
    assert created.status_code == 201

    updated = client.put(
        "/api/libraries/demo/overlays/contract-overlay",
        json={"name": "contract-overlay", "content": "description: updated\n", "run_validation": False},
    )
    assert updated.status_code == 200

    deleted = client.delete("/api/libraries/demo/overlays/contract-overlay")
    assert deleted.status_code in (200, 204)


# --- Datasets CRUD (apiCalls: fetchDatasetsList, create/update/delete) ---


def test_contract_datasets_crud(client, sample_lab):
    listed = client.get("/api/libraries/demo/datasets").json()
    assert "datasets" in listed

    detail = client.get("/api/libraries/demo/datasets/queries.yaml").json()
    assert "content" in detail

    created = client.post(
        "/api/libraries/demo/datasets",
        json={"name": "contract-ds.yaml", "content": "metadata:\n  name: contract-ds\nitems: []\n"},
    )
    assert created.status_code == 201

    updated = client.put(
        "/api/libraries/demo/datasets/contract-ds.yaml",
        json={"name": "contract-ds.yaml", "content": "metadata:\n  name: contract-ds\nitems: []\n"},
    )
    assert updated.status_code == 200

    deleted = client.delete("/api/libraries/demo/datasets/contract-ds.yaml")
    assert deleted.status_code in (200, 204)


# --- Metrics (apiCalls: useEvalMetrics, useMceMetrics) ---


def test_contract_metrics(client):
    eval_metrics = client.get("/api/metrics/eval").json()
    assert isinstance(eval_metrics, dict)
    mce_metrics = client.get("/api/metrics/mce").json()
    assert isinstance(mce_metrics, dict)


# --- Registry / discovery / info (daemon surface; UI may adopt) ---


def test_contract_registry_defaults_discovery_info(client, monkeypatch):
    from mas.lab.controller import lab_registry

    class _FakeRegistry:
        def catalog(self):
            return {
                "runtime": {},
                "pipeline_steps": {},
                "defaults": {"models": [{"model": "gpt-4o-mini"}]},
                "design_patterns": [],
            }

        def agent_defaults(self):
            return {"design_pattern": {"type": "react"}, "models": []}

        def default_model(self):
            return "gpt-4o-mini"

    monkeypatch.setattr(
        lab_registry,
        "get_lab_registry",
        lambda _ws=None: _FakeRegistry(),
    )

    registry = client.get("/api/registry").json()
    assert "registry" in registry

    defaults = client.get("/api/defaults").json()
    assert "agent" in defaults
    assert "default_model" in defaults

    discovery = client.get("/api/discovery").json()
    assert isinstance(discovery, dict)

    info = client.get("/api/info").json()
    assert isinstance(info, dict)


def test_contract_runtime_runners(client):
    resp = client.get("/api/runtime-runners")
    assert resp.status_code == 200
    body = resp.json()
    assert "runners" in body
    ids = {r["id"] for r in body["runners"]}
    assert "mas" in ids


def test_contract_experiment_definitions(client):
    resp = client.get("/api/experiments/definitions")
    assert resp.status_code == 200
    body = resp.json()
    assert "experiments" in body
    assert isinstance(body["experiments"], list)


def test_contract_benchmark_analyze(mock_submit_job, client):
    analyze = client.post(
        "/api/libraries/demo/benchmark/analyze",
        json={"benchmark_id": "demo-run-1"},
    )
    assert analyze.status_code == 202
    assert "job_id" in analyze.json()


def test_contract_benchmark_export(mock_submit_job, client):
    export = client.post(
        "/api/libraries/demo/benchmark/export",
        json={"benchmark_id": "demo-run-1", "dry_run": True},
    )
    assert export.status_code == 202
    body = export.json()
    assert "job_id" in body
    assert "mas-lab" in body["command"]
    assert "export" in body["command"]


def test_contract_benchmark_import(mock_submit_job, client):
    imp = client.post(
        "/api/libraries/demo/benchmark/import",
        json={"tarball": "/tmp/demo-run.tar.gz", "dry_run": True},
    )
    assert imp.status_code == 202
    body = imp.json()
    assert "job_id" in body
    assert "import" in body["command"]


def test_contract_topologies(client, sample_lab):
    (sample_lab / "topologies").mkdir(exist_ok=True)
    (sample_lab / "topologies" / "linear.yaml").write_text("name: linear\n", encoding="utf-8")

    resp = client.get("/api/libraries/demo/topologies")
    assert resp.status_code == 200
    assert "linear.yaml" in resp.json()["topologies"]


def test_contract_multi_turn_and_eval_output(mock_submit_job, client):
    mt = client.post(
        "/api/libraries/demo/run/multi-turn",
        json={
            "manifest_yaml": "kind: Agent\n",
            "queries": ["q1", "q2"],
            "verbose": False,
        },
    )
    assert mt.status_code == 202
    assert "job_id" in mt.json()

    ev = client.post(
        "/api/libraries/demo/eval-output",
        json={"events_file": "events.jsonl", "metrics": ["AnswerRelevancyMetric"]},
    )
    assert ev.status_code == 202
    assert "job_id" in ev.json()


def test_contract_job_cancel_and_clear(mock_submit_job, client):
    submit = client.post(
        "/api/libraries/demo/benchmark/run",
        json={"experiment_yaml": "metadata:\n  name: t\n", "progress": False},
    )
    job_id = submit.json()["job_id"]

    cancel = client.delete(f"/api/jobs/{job_id}")
    assert cancel.status_code == 200
    assert cancel.json().get("job_id") == job_id or "message" in cancel.json()

    cleared = client.delete("/api/jobs")
    assert cleared.status_code == 200
    assert "removed" in cleared.json()
