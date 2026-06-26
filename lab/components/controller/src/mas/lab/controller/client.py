#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unix-socket JSON-RPC client for the controller daemon."""
from __future__ import annotations

import atexit
import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mas.lab.controller import config as cfg
from mas.lab.controller.config import DEFAULT_HTTP_PORT, ensure_mas_dirs

logger = logging.getLogger(__name__)

_process_session_id: str | None = None
_process_session_registered = False


def _release_process_session() -> None:
    global _process_session_id
    if not _process_session_id:
        return
    try:
        ControllerClient().call(
            "release_session",
            {"session_id": _process_session_id},
            timeout=5.0,
        )
    except Exception:
        pass
    _process_session_id = None


def _register_process_session(client: ControllerClient) -> str:
    """Acquire one daemon session per OS process (CLI or test subprocess)."""
    global _process_session_id, _process_session_registered
    if _process_session_id is None:
        _process_session_id = f"cli-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    if not _process_session_registered:
        atexit.register(_release_process_session)
        _process_session_registered = True
    client.call("acquire_session", {"session_id": _process_session_id}, timeout=5.0)
    return _process_session_id


class ControllerClient:
    def __init__(self, socket_path: Path | None = None) -> None:
        self.socket_path = Path(socket_path or cfg.socket_path())

    def is_running(self) -> bool:
        if not self.socket_path.exists():
            return False
        try:
            self.call("ping")
            return True
        except OSError:
            return False

    def call(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> Any:
        payload = json.dumps({"method": method, "params": params or {}}).encode("utf-8")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(str(self.socket_path))
            sock.sendall(payload + b"\n")
            chunks: list[bytes] = []
            while True:
                part = sock.recv(65536)
                if not part:
                    break
                chunks.append(part)
                if b"\n" in part:
                    break
            raw = b"".join(chunks).split(b"\n", 1)[0]
            data = json.loads(raw.decode("utf-8"))
            if "error" in data:
                raise RuntimeError(data["error"])
            return data.get("result")
        finally:
            sock.close()

    def ensure_running(self, *, port: int = DEFAULT_HTTP_PORT, auto_start: bool = True) -> None:
        if self.is_running():
            _register_process_session(self)
            return
        if not auto_start:
            raise RuntimeError(
                f"Controller daemon is not running (socket {self.socket_path}). "
                "Start it with: mas-lab control start"
            )
        start_daemon(port=port, detach=True)
        for _ in range(40):
            if self.is_running():
                _register_process_session(self)
                return
            time.sleep(0.25)
        raise RuntimeError("Controller daemon failed to start")


def controller_session(*, port: int = DEFAULT_HTTP_PORT) -> ControllerClient:
    """Context manager: ensure daemon + acquire session; release on exit."""
    client = ControllerClient()
    client.ensure_running(port=port, auto_start=True)
    return client


def start_daemon(*, port: int = DEFAULT_HTTP_PORT, detach: bool = True, foreground: bool = False) -> None:
    ensure_mas_dirs()
    cmd = [
        sys.executable,
        "-m",
        "mas.lab.controller.daemon",
        "--port",
        str(port),
    ]
    if os.environ.get("MAS_CONTROLLER_NO_HTTP", "1").strip().lower() in ("1", "true", "yes"):
        cmd.append("--no-http")
    if foreground:
        subprocess.run(cmd, check=False)
        return
    env = os.environ.copy()
    env.setdefault("MAS_CONTROLLER_PORT", str(port))
    log_path = Path(os.environ.get("MAS_CONTROLLER_LOG", cfg.controller_dir() / "daemon.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=detach,
        env=env,
    )


def stop_daemon() -> bool:
    client = ControllerClient()
    if not client.is_running():
        cfg.pid_path().unlink(missing_ok=True)
        cfg.socket_path().unlink(missing_ok=True)
        return True
    try:
        client.call("shutdown")
    except Exception:
        pass
    cfg.pid_path().unlink(missing_ok=True)
    cfg.socket_path().unlink(missing_ok=True)
    return True


def follow_worker(
    worker_id: str,
    *,
    timeout: float = 86400.0,
    poll: float = 0.5,
    stream: bool = True,
) -> Dict[str, Any]:
    """Poll worker state until terminal; optionally stream stdout/stderr deltas to the terminal."""
    import sys

    client = ControllerClient()
    client.ensure_running()
    last_stdout = ""
    last_stderr = ""
    deadline = time.time() + timeout
    terminal = {"completed", "failed", "cancelled"}

    while time.time() < deadline:
        detail = client.call("get_worker", {"worker_id": worker_id})
        if detail is None:
            raise RuntimeError(f"Worker {worker_id!r} not found")

        if stream:
            stdout = detail.get("stdout") or ""
            stderr = detail.get("stderr") or ""
            if len(stdout) > len(last_stdout):
                sys.stdout.write(stdout[len(last_stdout) :])
                sys.stdout.flush()
                last_stdout = stdout
            if len(stderr) > len(last_stderr):
                sys.stderr.write(stderr[len(last_stderr) :])
                sys.stderr.flush()
                last_stderr = stderr

        status = detail.get("status")
        if status in terminal:
            return detail
        time.sleep(poll)

    raise TimeoutError(f"Worker {worker_id!r} did not finish within {timeout}s")


def wait_for_worker(
    worker_id: str,
    *,
    timeout: float = 86400.0,
    poll: float = 1.0,
    stream: bool = False,
) -> Dict[str, Any]:
    """Wait for a worker to finish (optional streaming via :func:`follow_worker`)."""
    return follow_worker(worker_id, timeout=timeout, poll=poll, stream=stream)
