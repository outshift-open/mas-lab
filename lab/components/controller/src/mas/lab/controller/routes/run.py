#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agent and MAS run endpoints."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter

from mas.lab.controller.constants import WEB_SEARCH_CACHE_DIR
from mas.lab.controller.models import MultiTurnRequest, RunAgentRequest, RunMASRequest
from mas.lab.controller.routes._api import deps, jobs, LIBRARIES_DIR, validate_pipeline_yaml

router = APIRouter()


@router.post("/api/libraries/{library_name}/run", tags=["Libraries"], status_code=202)
async def run_agent(library_name: str, req: RunAgentRequest):
    """Run an agent with a single query in-process. Returns a job_id for polling."""
    lib_dir = deps.get_library_path(library_name)

    if req.no_cache and WEB_SEARCH_CACHE_DIR.exists():
        shutil.rmtree(WEB_SEARCH_CACHE_DIR, ignore_errors=True)

    job = jobs.submit_agent_chat_job(
        endpoint=f"/api/libraries/{library_name}/run",
        manifest_yaml=req.manifest_yaml,
        query=req.query,
        lib_dir=lib_dir,
        flavour=req.flavour,
        session_id=req.session_id,
        timeout=req.timeout,
        request_body={"query": req.query, "flavour": req.flavour},
    )
    return {
        "job_id": job.id,
        "status": job.status.value,
        "session_id": job.session_id,
        "command": job.command,
    }


@router.post("/api/libraries/{library_name}/run/multi-turn", tags=["Libraries"], status_code=202)
async def run_agent_multi_turn(library_name: str, req: MultiTurnRequest):
    """Run an agent with multiple sequential queries. Returns a job_id for polling."""
    lib_dir = deps.get_library_path(library_name)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="agent-mt-", delete=False, dir=str(lib_dir)
    )
    tmp.write(req.manifest_yaml)
    tmp.close()
    tmp_path = Path(tmp.name)

    cmd = ["mas-runtime", "run-agent", tmp_path.name]
    if req.verbose:
        cmd.append("-v")
    for ov in req.overlays:
        cmd += ["--overlay", ov]
    if req.flavour:
        cmd += ["--flavour", req.flavour]
    for q in req.queries:
        cmd += ["-q", q]
    job = jobs.submit_job(
        endpoint=f"/api/libraries/{library_name}/run/multi-turn",
        cmd=cmd,
        cwd=lib_dir,
        timeout=req.timeout,
        request_body=req.model_dump(),
        cleanup_paths=[tmp_path],
    )
    return {"job_id": job.id, "status": job.status.value, "command": job.command}


@router.post("/api/libraries/{library_name}/run-mas", tags=["Libraries"], status_code=202)
async def run_mas(library_name: str, req: RunMASRequest):
    """Run a MAS with a single query. Returns a job_id for polling."""
    lib_dir = deps.get_library_path(library_name)

    # Write temp file inside apps/ so agent ref paths resolve as siblings.
    apps_dir = lib_dir / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="mas-run-", delete=False, dir=str(apps_dir)
    )
    tmp.write(req.manifest_yaml)
    tmp.close()
    tmp_path = Path(tmp.name)

    cmd = ["mas-ctl", "run-mas", str(tmp_path.relative_to(lib_dir))]
    if req.verbose:
        cmd.append("-v")
    for ov in req.overlays:
        cmd += ["--overlay", ov]
    if req.flavour:
        cmd += ["--flavour", req.flavour]
    # Auto-inject infra refs so model mappings and tool providers are discovered.
    # Check library-local infra/ and workspace-root infra/ (parent of library dir).
    _seen_infra: set[Path] = set()
    for infra_dir in [lib_dir / "infra", lib_dir.parent / "infra"]:
        if infra_dir.is_dir():
            for infra_file in sorted(infra_dir.glob("*.yaml")):
                resolved = infra_file.resolve()
                if resolved not in _seen_infra:
                    _seen_infra.add(resolved)
                    cmd += ["--infra-ref", str(infra_file)]
    cmd += ["-q", req.query]
    job = jobs.submit_job(
        endpoint=f"/api/libraries/{library_name}/run-mas",
        cmd=cmd,
        cwd=lib_dir,
        timeout=req.timeout,
        request_body={"query": req.query, "flavour": req.flavour},
        cleanup_paths=[tmp_path],
    )
    return {"job_id": job.id, "status": job.status.value, "command": job.command}
