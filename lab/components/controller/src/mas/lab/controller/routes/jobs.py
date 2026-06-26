#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Job management endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from mas.lab.controller.jobs import JobStatus, _jobs

router = APIRouter()


@router.get("/api/jobs", tags=["Jobs"])
async def list_jobs(status: Optional[str] = None):
    """List all jobs. Optionally filter by status (running, completed, failed, etc.)."""
    jobs = _jobs.values()
    if status:
        jobs = [j for j in jobs if j.status.value == status]
    else:
        jobs = list(jobs)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return {"jobs": [j.to_summary() for j in jobs]}


@router.get("/api/jobs/{job_id}", tags=["Jobs"])
async def get_job(job_id: str):
    """Get full details of a specific job (including stdout/stderr)."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.to_dict()


@router.delete("/api/jobs/{job_id}", tags=["Jobs"])
async def cancel_job(job_id: str):
    """Cancel a running job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        return {"message": f"Job already in terminal state: {job.status.value}"}
    if job._task and not job._task.done():
        job._task.cancel()
    return {"message": "Cancellation requested", "job_id": job_id}


@router.delete("/api/jobs", tags=["Jobs"])
async def clear_finished_jobs():
    """Remove all completed/failed/cancelled/timeout jobs from the list."""
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMEOUT}
    to_remove = [jid for jid, j in _jobs.items() if j.status in terminal]
    for jid in to_remove:
        del _jobs[jid]
    return {"removed": len(to_remove)}
