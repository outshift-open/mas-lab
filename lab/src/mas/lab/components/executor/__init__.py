#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ExecutionContext:
    run_id: str
    env: Dict[str, str]
    cwd: Optional[str]
    command: list[str]
    # Library mode extension
    entry_point: Optional[tuple[str, str]] = None # (module, function)
    # Kwargs for library function call
    kwargs: Optional[Dict[str, Any]] = None


class AgentExecutor(ABC):
    """Abstract base class for executing agents."""

    @abstractmethod
    def start(self, context: ExecutionContext) -> None:
        """Start the agent execution."""
        pass

    @abstractmethod
    def stop(self, run_id: str) -> None:
        """Stop the execution."""
        pass

    @abstractmethod
    def is_running(self, run_id: str) -> bool:
        """Check if execution is active."""
        pass


class InProcessExecutor(AgentExecutor):
    """Executes agents as a library call in a separate thread."""
    
    def __init__(self):
        self._threads: Dict[str, threading.Thread] = {}
        self._active: Dict[str, bool] = {}

    def start(self, context: ExecutionContext) -> None:
        if not context.entry_point:
            raise ValueError("InProcessExecutor requires entry_point (module, function)")
            
        module_name, func_name = context.entry_point
        
        def _wrapper():
            # Inject environment variables
            old_env = os.environ.copy()
            os.environ.update(context.env)
            
            # Change CWD if needed
            old_cwd = os.getcwd()
            path_inserted = False
            
            if context.cwd:
                os.chdir(context.cwd)
                if context.cwd not in sys.path:
                    sys.path.insert(0, context.cwd)
                    path_inserted = True

            try:
                import importlib
                # Force reload to pick up changes if module was imported before
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    module = importlib.import_module(module_name)
                
                func = getattr(module, func_name)
                # Call entry point with kwargs if provided
                if context.kwargs:
                    func(**context.kwargs)
                else:
                    func()
            except Exception as e:
                print(f"Error in InProcessExecutor: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Restore environment (mostly best effort)
                os.chdir(old_cwd)
                if path_inserted:
                    sys.path.pop(0)
                os.environ.clear()
                os.environ.update(old_env)
                if context.run_id in self._active:
                    del self._active[context.run_id]

        thread = threading.Thread(target=_wrapper, daemon=True)
        self._threads[context.run_id] = thread
        self._active[context.run_id] = True
        thread.start()

    def stop(self, run_id: str) -> None:
        # In-process stop is hard without cooperation
        # We can only flag it as stopped in our tracking
        if run_id in self._active:
            del self._active[run_id]
        # Real implementation needs an abort signal or async cancellation

    def is_running(self, run_id: str) -> bool:
        return run_id in self._active and self._threads[run_id].is_alive()


def _load_pid_map(pid_file: Path) -> Dict[str, int]:
    if not pid_file.exists():
        return {}
    try:
        payload = json.loads(pid_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {key: int(value) for key, value in payload.items() if isinstance(value, (int, str))}


def _write_pid_map(pid_file: Path, payload: Dict[str, int]) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(json.dumps(payload), encoding="utf-8")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _pids_on_port(port: int) -> list[int]:
    cmd = ["lsof", "-t", "-i", f":{port}"]
    pid_bytes = subprocess.check_output(cmd)
    pids = []
    for pid_str in pid_bytes.decode().strip().split("\n"):
        if pid_str:
            try:
                pids.append(int(pid_str))
            except ValueError:
                continue
    return pids


def _terminate_pid(pid: int, logger=None) -> None:
    try:
        if logger:
            logger.info(f"Terminating process {pid}")
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return
    try:
        os.kill(pid, 0)
    except Exception:
        return
    try:
        if logger:
            logger.info(f"Killing process {pid}")
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


def kill_port(port: int, *, force: bool = False, pid_file: Path | None = None, logger=None) -> list[int]:
    """Best-effort termination of processes listening on a port.

    Only acts when force=True. If a pid file is provided, it tries those PIDs first.
    """
    if not force:
        return []
    try:
        candidates = _pids_on_port(port)
    except Exception:
        return []
    if not candidates:
        return []
    tracked = None
    if pid_file:
        tracked = set(_load_pid_map(pid_file).values())
    if tracked:
        candidates = [pid for pid in candidates if pid in tracked] or candidates
    for pid in candidates:
        _terminate_pid(pid, logger=logger)
    return candidates


class LocalExecutor(AgentExecutor):
    """Executes agents as local subprocesses."""

    def __init__(self, pid_file: Path | None = None):
        self._processes: Dict[str, subprocess.Popen] = {}
        self.pid_file = pid_file or Path(os.getenv("MAS_LAB_PID_FILE", "logs/mas_lab_pids.json"))

    def start(self, context: ExecutionContext) -> None:
        """Launches the process."""
        process = subprocess.Popen(
            context.command,
            env=context.env,
            cwd=context.cwd
            # stdout/stderr inherited by default, or we could pipe them
        )
        self._processes[context.run_id] = process
        pid_map = _load_pid_map(self.pid_file)
        pid_map[context.run_id] = process.pid
        _write_pid_map(self.pid_file, pid_map)

    def stop(self, run_id: str) -> None:
        process = self._processes.get(run_id)
        if process:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    if process.poll() is None:
                        process.kill()
            del self._processes[run_id]
        pid_map = _load_pid_map(self.pid_file)
        if run_id in pid_map:
            del pid_map[run_id]
            _write_pid_map(self.pid_file, pid_map)

    def is_running(self, run_id: str) -> bool:
        process = self._processes.get(run_id)
        if process is None:
            return False
        running = process.poll() is None
        if not running:
            pid_map = _load_pid_map(self.pid_file)
            if run_id in pid_map:
                del pid_map[run_id]
                _write_pid_map(self.pid_file, pid_map)
        return running
