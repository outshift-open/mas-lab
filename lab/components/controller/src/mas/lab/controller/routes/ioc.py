#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""IoC catalog, overlay, run, and results endpoints.

Serves the challenge catalog and overlay YAML content from the external
``IOC_REPO`` (ioc-core-mas-lab checkout). The catalog is cached and
auto-refreshes when its mtime changes.

The run endpoint submits an IoC reproduction run as a background job,
delegating to ``{IOC_REPO}/eval/run_ioc.py``.

The results endpoints read the evaluator output from a completed run and
return the delta report, run metadata, and per-rep evidence.
"""

from __future__ import annotations

import csv
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from mas.lab.controller.constants import (
    CLARIS_LIB,
    EVALUATOR_ENV,
    IOC_REPO,
    IOC_RUN_TIMEOUT,
    IOC_RUNS_ROOT,
    MAS_CTL_MODEL,
    MAS_LAB_OSS,
)
from mas.lab.controller.ioc_catalog import get_ioc_catalog_provider
from mas.lab.controller.models import IocRunRequest
from mas.lab.controller.routes._api import jobs

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IoC"])


def _require_ioc_provider():
    """Return the catalog provider or raise 503."""
    try:
        return get_ioc_catalog_provider()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _check_ioc_env() -> dict[str, str]:
    """Validate that required IoC environment paths exist.

    Returns the env_override dict for ``submit_job``.
    Raises HTTPException(503) with an actionable message on failure.
    """
    missing: list[str] = []
    if MAS_LAB_OSS is None or not MAS_LAB_OSS.is_dir():
        missing.append(
            f"MAS_LAB_OSS={'<not set>' if MAS_LAB_OSS is None else MAS_LAB_OSS}"
        )
    if CLARIS_LIB is None or not CLARIS_LIB.is_dir():
        missing.append(
            f"CLARIS_LIB={'<not set>' if CLARIS_LIB is None else CLARIS_LIB}"
        )
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                "IoC run environment is not configured. "
                f"Missing or invalid: {', '.join(missing)}. "
                "Set them to valid directory paths and restart."
            ),
        )

    env: dict[str, str] = {
        "MAS_LAB_OSS": str(MAS_LAB_OSS),
        "CLARIS_LIB": str(CLARIS_LIB),
    }

    if EVALUATOR_ENV is not None:
        env_path = Path(EVALUATOR_ENV)
        if not env_path.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    f"EVALUATOR_ENV={EVALUATOR_ENV} does not exist or is not a file. "
                    "Fix the path or unset it to use the default."
                ),
            )
        env["EVALUATOR_ENV"] = str(env_path)

    if MAS_CTL_MODEL is not None:
        env["MAS_CTL_MODEL"] = MAS_CTL_MODEL

    if IOC_REPO is not None:
        env["IOC_REPO"] = str(IOC_REPO)

    return env


# ---------------------------------------------------------------------------
# GET /api/ioc/catalog
# ---------------------------------------------------------------------------

@router.get("/api/ioc/catalog")
async def ioc_catalog():
    """Return the full IoC challenge catalog (apps, challenges, overlays, metrics)."""
    provider = _require_ioc_provider()
    try:
        return provider.get_catalog()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /api/ioc/overlays/{id}
# ---------------------------------------------------------------------------

@router.get("/api/ioc/overlays/{overlay_id:path}")
async def ioc_overlay(overlay_id: str):
    """Return the YAML content of a specific IoC overlay by catalog id.

    The ``overlay_id`` uses the catalog's ``id`` field (e.g. ``sre/cr1-divergent-goal``).
    Only ids present in the catalog are served — arbitrary paths are rejected.
    """
    provider = _require_ioc_provider()
    try:
        return provider.get_overlay_content(overlay_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Overlay '{overlay_id}' not found in the IoC catalog.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /api/ioc/runs
# ---------------------------------------------------------------------------

@router.post("/api/ioc/runs", status_code=202)
async def ioc_run(req: IocRunRequest):
    """Submit an IoC reproduction run as a background job.

    Validates the request against the catalog, builds the ``run_ioc.py``
    command, and submits it via the shared job machinery.
    """
    provider = _require_ioc_provider()
    try:
        catalog = provider.get_catalog()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # --- Validate app ---
    apps = catalog.get("apps") or {}
    if req.app not in apps:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown app '{req.app}'. Available: {list(apps.keys())}",
        )

    # --- Validate overlay ids belong to this app ---
    app_data = apps[req.app]
    app_overlay_ids: set[str] = set()
    for challenge in app_data.get("challenges", []):
        for ov in challenge.get("overlays", []):
            app_overlay_ids.add(ov["id"])

    bad_ids = [oid for oid in req.overlays if oid not in app_overlay_ids]
    if bad_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown overlay id(s) for app '{req.app}': {bad_ids}. "
                f"Valid ids: {sorted(app_overlay_ids)}"
            ),
        )

    # --- Validate environment ---
    env_override = _check_ioc_env()

    # --- Build workspace ---
    assert IOC_REPO is not None  # guarded by _require_ioc_provider
    run_id = str(uuid.uuid4())
    workspace = IOC_RUNS_ROOT / run_id
    IOC_RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    # --- Build command ---
    runner = IOC_REPO / "eval" / "run_ioc.py"
    cmd: list[str] = [
        sys.executable,
        str(runner),
        "--app", req.app,
        "--reps", str(req.reps),
    ]
    if req.query is not None:
        cmd += ["--query", req.query]
    for oid in req.overlays:
        cmd += ["--overlay", oid]
    cmd += [
        "--bundle", str(workspace / "bundle"),
        "--out", str(workspace / "out"),
        "--json",
    ]

    # --- Compute timeout ---
    trace_count = req.reps * (len(req.overlays) + 1)
    timeout = max(IOC_RUN_TIMEOUT, trace_count * 150)

    # --- Submit ---
    out_dir = str(workspace / "out")
    bundle_dir = str(workspace / "bundle")
    job = jobs.submit_job(
        endpoint="ioc/run",
        cmd=cmd,
        cwd=IOC_REPO,
        timeout=timeout,
        env_override=env_override,
        request_body={
            **req.model_dump(),
            "run_id": run_id,
            "workspace": str(workspace),
            "out": out_dir,
            "bundle": bundle_dir,
        },
    )

    logger.info(
        "IoC run job %s submitted: app=%s, overlays=%s, reps=%d, "
        "traces=%d, timeout=%ds, workspace=%s",
        job.id, req.app, req.overlays, req.reps,
        trace_count, timeout, workspace,
    )

    return {
        "job_id": job.id,
        "status": job.status.value,
        "command": job.command,
        "run_id": run_id,
        "workspace": str(workspace),
        "trace_count": trace_count,
    }


# ---------------------------------------------------------------------------
# Shared helpers for results / evidence
# ---------------------------------------------------------------------------

def _load_ioc_job(job_id: str) -> Any:
    """Load a job, verify it's an IoC run, return it.

    Raises HTTPException on unknown id or wrong endpoint.
    """
    from mas.lab.controller.jobs import _jobs

    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.endpoint != "ioc/run":
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is not an IoC run (endpoint={job.endpoint}).",
        )
    return job


def _require_completed_run(job: Any) -> Path:
    """Return the ``out`` dir for a completed IoC run.

    Returns 202 for pending/running jobs, 422 for failed/partial.
    """
    from mas.lab.controller.jobs import TERMINAL_STATUSES

    rb = job.request_body or {}
    out_dir = rb.get("out")
    if not out_dir:
        out_dir = rb.get("workspace")
        if out_dir:
            out_dir = str(Path(out_dir) / "out")

    if job.status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=202,
            detail={"status": job.status.value, "message": "Run is still in progress."},
        )

    out_path = Path(out_dir) if out_dir else None
    csv_path = out_path / "results" / "metrics_long.csv" if out_path else None

    if job.status.value not in ("completed",) or not csv_path or not csv_path.is_file():
        detail_msg = f"Run {job.id} did not produce results (status={job.status.value})."
        if job.error:
            detail_msg += f" Error: {job.error}"
        raise HTTPException(status_code=422, detail=detail_msg)

    return out_path


def _run_delta_report(csv_path: Path) -> dict[str, Any]:
    """Run ``delta_report.py --json`` and return the parsed report."""
    assert IOC_REPO is not None
    script = IOC_REPO / "eval" / "delta_report.py"

    result = subprocess.run(
        [sys.executable, str(script), "--json", str(csv_path)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(IOC_REPO),
    )

    if result.returncode != 0:
        logger.error("delta_report.py failed: %s", result.stderr)
        raise HTTPException(
            status_code=500,
            detail=f"delta_report.py failed: {result.stderr.strip()[-500:]}",
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"delta_report.py produced invalid JSON: {exc}",
        ) from exc


def _load_study_summary(out_path: Path) -> dict[str, Any]:
    """Read ``study_summary.json``; return empty dict on missing/malformed."""
    summary_path = out_path / "results" / "study_summary.json"
    if not summary_path.is_file():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _build_challenge_name_map(catalog: dict[str, Any], app_key: str) -> dict[str, str]:
    """Map scenario id (e.g. ``cr1-divergent-goal``) to display name."""
    apps = catalog.get("apps") or {}
    app_data = apps.get(app_key) or {}
    name_map: dict[str, str] = {}
    for challenge in app_data.get("challenges", []):
        for ov in challenge.get("overlays", []):
            overlay_id = ov.get("id", "")
            short = overlay_id.split("/", 1)[-1] if "/" in overlay_id else overlay_id
            name_map[short] = challenge.get("name", short)
    return name_map


# ---------------------------------------------------------------------------
# GET /api/ioc/runs/{job_id}/results
# ---------------------------------------------------------------------------

@router.get("/api/ioc/runs/{job_id}/results")
async def ioc_run_results(job_id: str):
    """Return the delta report and run metadata for a completed IoC run."""
    job = _load_ioc_job(job_id)
    out_path = _require_completed_run(job)

    csv_path = out_path / "results" / "metrics_long.csv"
    report = _run_delta_report(csv_path)

    summary = _load_study_summary(out_path)

    rb = job.request_body or {}
    app_key = rb.get("app", "")

    cost_usd = summary.get("estimated_cost_usd")
    completed_trajectories = summary.get("completed_trajectories")

    model = summary.get("model")
    models: dict[str, str] = {}
    if model:
        models["agents"] = model
    judge_model = summary.get("judge_model") or model
    if judge_model:
        models["judge"] = judge_model

    app_display_name = app_key
    challenge_names: dict[str, str] = {}
    try:
        provider = _require_ioc_provider()
        catalog = provider.get_catalog()
        apps = catalog.get("apps") or {}
        if app_key in apps:
            app_display_name = apps[app_key].get("display_name", app_key)
        challenge_names = _build_challenge_name_map(catalog, app_key)
    except Exception:
        pass

    for ch in report.get("challenges", []):
        scenario = ch.get("scenario", "")
        if scenario in challenge_names:
            ch["display_name"] = challenge_names[scenario]

    run_block = {
        "app": app_key,
        "app_display_name": app_display_name,
        "reps": rb.get("reps"),
        "models": models,
        "traces": completed_trajectories,
        "cost_usd": cost_usd,
        "finished_at": job.finished_at,
        "query": rb.get("query"),
        "status": job.status.value,
    }

    return {
        "run": run_block,
        **report,
    }


# ---------------------------------------------------------------------------
# GET /api/ioc/runs/{job_id}/evidence
# ---------------------------------------------------------------------------

@router.get("/api/ioc/runs/{job_id}/evidence")
async def ioc_run_evidence(
    job_id: str,
    scenario: str = Query(..., description="Scenario id (e.g. cr1-divergent-goal or NONE-baseline)"),
    metric: str = Query(..., description="Metric name (e.g. Goal Alignment)"),
):
    """Return per-rep judge evidence for a given scenario + metric."""
    job = _load_ioc_job(job_id)
    out_path = _require_completed_run(job)

    csv_path = out_path / "results" / "metrics_long.csv"
    report = _run_delta_report(csv_path)

    valid_scenarios = {ch["scenario"] for ch in report.get("challenges", [])}
    for bl_name in report.get("baselines", {}):
        valid_scenarios.add(bl_name)
    valid_metrics = set(report.get("metrics", []))

    if scenario not in valid_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{scenario}'. Valid: {sorted(valid_scenarios)}",
        )
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric '{metric}'. Valid: {sorted(valid_metrics)}",
        )

    reps: list[dict[str, Any]] = []
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rep_counter = 0
            for row in reader:
                row_scenario = row.get("scenario", "")
                row_metric = row.get("metric", "")
                if row_scenario != scenario or row_metric != metric:
                    continue
                rep_counter += 1
                score_raw = row.get("score", "")
                try:
                    score = float(score_raw)
                except (ValueError, TypeError):
                    score = None
                fatal_raw = row.get("fatal_failures", "0")
                try:
                    fatal_failures = int(fatal_raw)
                except (ValueError, TypeError):
                    fatal_failures = 0
                reps.append({
                    "rep": rep_counter,
                    "failed": score == 0,
                    "score": score,
                    "fatal_failures": fatal_failures,
                    "reasoning": row.get("reasoning", ""),
                    "evidence_ids": (row.get("evidence_ids") or "").split("|") if row.get("evidence_ids") else [],
                })
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read metrics CSV: {exc}",
        ) from exc

    return {
        "scenario": scenario,
        "metric": metric,
        "reps": reps,
    }
