#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Background job tracking and execution."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


TERMINAL_STATUSES = frozenset({
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.TIMEOUT,
    JobStatus.INTERRUPTED,
})


@dataclass
class Job:
    id: str
    endpoint: str
    command: str
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    response: str = ""
    error_message: str = ""
    error_detail: str = ""
    session_id: str = ""
    request_body: dict = field(default_factory=dict)
    log_path: Optional[str] = None
    _proc: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "endpoint": self.endpoint,
            "command": self.command,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "response": self.response,
            "error_message": self.error_message,
            "error_detail": self.error_detail,
            "session_id": self.session_id,
            "request_body": self.request_body,
        }
        if self.log_path and not self.stdout:
            d["stdout"] = _read_log_tail(self.log_path)
        return d

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "endpoint": self.endpoint,
            "command": self.command,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "pid": self.pid,
            "exit_code": self.exit_code,
        }

    def _persistable_dict(self) -> dict[str, Any]:
        """Fields that the store cares about (no stdout/stderr/runtime)."""
        return {
            "id": self.id,
            "endpoint": self.endpoint,
            "command": self.command,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "error": self.error,
            "request_body": self.request_body,
            "log_path": self.log_path,
        }


def _read_log_tail(log_path: str, max_bytes: int = 64 * 1024) -> str:
    """Read the tail of a log file, returning at most *max_bytes* characters."""
    try:
        p = Path(log_path)
        if not p.is_file():
            return ""
        size = p.stat().st_size
        with p.open("r", encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            return f.read()
    except OSError:
        return ""


def _resolve_log_path(job: Job) -> Path | None:
    """Determine where to write the run log for a job.

    Prefers ``{workspace}/out/run.log`` when a workspace is carried in
    ``request_body``; falls back to a per-job file under the mas data dir.
    """
    rb = job.request_body or {}
    workspace = rb.get("workspace")
    if workspace:
        out_dir = Path(workspace) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / "run.log"

    from mas.lab.controller.constants import MAS_LAB_ROOT
    logs_dir = MAS_LAB_ROOT / "job-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{job.id}.log"


def _persist(job: Job) -> None:
    """Save a job to the durable store (no-op if ephemeral)."""
    from mas.lab.controller.job_store import get_job_store
    try:
        get_job_store().save(job._persistable_dict())
    except Exception:
        logger.warning("Failed to persist job %s", job.id, exc_info=True)


_jobs: dict[str, Job] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jobs_from_store() -> None:
    """Populate ``_jobs`` from the durable store on startup."""
    from mas.lab.controller.job_store import get_job_store
    store = get_job_store()
    rows = store.load_all()
    for row in rows:
        status_val = row.get("status", "failed")
        try:
            status = JobStatus(status_val)
        except ValueError:
            status = JobStatus.FAILED

        job = Job(
            id=row["id"],
            endpoint=row.get("endpoint", ""),
            command=row.get("command", ""),
            status=status,
            created_at=row.get("created_at", ""),
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            pid=row.get("pid"),
            exit_code=row.get("exit_code"),
            error=row.get("error"),
            request_body=row.get("request_body") or {},
            log_path=row.get("log_path"),
        )
        _jobs[job.id] = job
    logger.info("Loaded %d jobs from store", len(rows))


def reconcile_jobs() -> None:
    """Mark non-terminal jobs appropriately after a server restart.

    Any job still ``pending`` or ``running`` had its subprocess lost.
    If the runner left results on disk, mark ``completed``; otherwise
    mark ``interrupted``.
    """
    for job in _jobs.values():
        if job.status in TERMINAL_STATUSES:
            continue

        rb = job.request_body or {}
        workspace = rb.get("workspace")
        results_exist = False
        if workspace:
            results_csv = Path(workspace) / "out" / "results" / "metrics_long.csv"
            results_exist = results_csv.is_file()

        if results_exist:
            job.status = JobStatus.COMPLETED
            job.error = None
            logger.info(
                "Job %s reconciled → completed (results found on disk)", job.id
            )
        else:
            job.status = JobStatus.INTERRUPTED
            job.error = "Server restarted while running; subprocess lost"
            logger.info("Job %s reconciled → interrupted", job.id)

        job.finished_at = job.finished_at or now_iso()
        _persist(job)


async def run_job(
    job: Job,
    cmd: list[str],
    cwd: Path,
    timeout: int,
    env: dict,
    cleanup_paths: list[Path] | None = None,
) -> None:
    """Background coroutine that executes the command and updates the job."""
    job.status = JobStatus.RUNNING
    job.started_at = now_iso()

    log_file = _resolve_log_path(job)
    if log_file:
        job.log_path = str(log_file)
    _persist(job)

    log_handle = None
    try:
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_file.open("w", encoding="utf-8", errors="replace")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        job.pid = proc.pid
        job._proc = proc

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        job.exit_code = proc.returncode
        job.stdout = stdout.decode(errors="replace")
        job.stderr = stderr.decode(errors="replace")

        if log_handle:
            log_handle.write(job.stdout)
            if job.stderr:
                log_handle.write("\n--- stderr ---\n")
                log_handle.write(job.stderr)

        job.status = JobStatus.COMPLETED if proc.returncode == 0 else JobStatus.FAILED
        if proc.returncode != 0:
            job.error = f"Command failed with exit code {proc.returncode}"

    except asyncio.TimeoutError:
        if job._proc:
            job._proc.kill()
            await job._proc.communicate()
        job.status = JobStatus.TIMEOUT
        job.error = f"Command timed out after {timeout}s"

    except asyncio.CancelledError:
        if job._proc and job._proc.returncode is None:
            job._proc.kill()
            await job._proc.communicate()
        job.status = JobStatus.CANCELLED
        job.error = "Job was cancelled"

    except FileNotFoundError:
        job.status = JobStatus.FAILED
        job.error = f"Command not found: {cmd[0]}. Ensure mas-runtime is on PATH."

    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)

    finally:
        job.finished_at = now_iso()
        job._proc = None
        if log_handle:
            try:
                log_handle.close()
            except OSError:
                pass
        if cleanup_paths:
            for p in cleanup_paths:
                p.unlink(missing_ok=True)
        _persist(job)


async def run_agent_chat_job(
    job: Job,
    manifest_yaml: str,
    query: str,
    lib_dir: Path,
    flavour: Optional[str],
    session_id: str,
    timeout: int,
) -> None:
    """Background coroutine: run one agent turn in-process (no subprocess)."""
    from mas.lab.controller.agent_chat import run_agent_turn

    job.status = JobStatus.RUNNING
    job.started_at = now_iso()
    _persist(job)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                run_agent_turn,
                manifest_yaml,
                query,
                base_dir=lib_dir,
                flavour=flavour,
                session_id=session_id,
            ),
            timeout=timeout,
        )
        job.response = result.response
        job.error_message = result.error_message
        job.error_detail = result.error_detail
        job.session_id = result.session_id

        if result.status == "ok":
            job.status = JobStatus.COMPLETED
            job.exit_code = 0
        else:
            job.status = JobStatus.FAILED
            job.exit_code = 1
            job.error = result.error_message

    except asyncio.TimeoutError:
        job.status = JobStatus.TIMEOUT
        job.error = f"Agent timed out after {timeout}s"
        job.error_message = job.error

    except asyncio.CancelledError:
        job.status = JobStatus.CANCELLED
        job.error = "Job was cancelled"
        job.error_message = job.error

    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.error_message = str(exc)

    finally:
        job.finished_at = now_iso()
        _persist(job)


def submit_agent_chat_job(
    endpoint: str,
    manifest_yaml: str,
    query: str,
    lib_dir: Path,
    flavour: Optional[str] = None,
    session_id: Optional[str] = None,
    timeout: int = 60,
    request_body: dict | None = None,
) -> Job:
    """Create a chat job, launch in-process agent turn, return immediately."""
    sid = session_id or str(uuid.uuid4())

    job = Job(
        id=str(uuid.uuid4()),
        endpoint=endpoint,
        command=f"agent-chat({lib_dir.name})",
        status=JobStatus.PENDING,
        created_at=now_iso(),
        session_id=sid,
        request_body=request_body or {},
    )
    _jobs[job.id] = job
    _persist(job)

    task = asyncio.create_task(
        run_agent_chat_job(
            job, manifest_yaml, query, lib_dir, flavour, sid, timeout,
        )
    )
    job._task = task

    logger.info("Agent chat job %s submitted (session=%s)", job.id, sid)
    return job


def submit_job(
    endpoint: str,
    cmd: list[str],
    cwd: Path,
    timeout: int = 60,
    env_override: dict[str, str] | None = None,
    request_body: dict | None = None,
    cleanup_paths: list[Path] | None = None,
) -> Job:
    """Create a job, launch it in the background, return immediately."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)

    job = Job(
        id=str(uuid.uuid4()),
        endpoint=endpoint,
        command=" ".join(cmd),
        status=JobStatus.PENDING,
        created_at=now_iso(),
        request_body=request_body or {},
    )
    _jobs[job.id] = job
    _persist(job)

    task = asyncio.create_task(run_job(job, cmd, cwd, timeout, env, cleanup_paths))
    job._task = task

    logger.info("Job %s submitted: %s", job.id, job.command)
    return job
