#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Benchmark run locking to prevent concurrent execution.

Uses PID-based lock files to avoid stale locks when process dies.
"""

import os
import socket
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class LockInfo:
    """Information about a lock."""
    pid: int
    hostname: str
    timestamp: str
    
    def is_alive(self) -> bool:
        """Check if the process that created this lock is still alive.
        
        Returns:
            True if process is alive
        """
        if not PSUTIL_AVAILABLE:
            # Without psutil, assume lock is valid
            logger.warning("psutil not available, cannot check if process is alive")
            return True
        
        try:
            process = psutil.Process(self.pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False


class BenchmarkLock:
    """PID-based lock for benchmark execution.
    
    Lock file format:
    ```
    PID: 12345
    HOSTNAME: myhost
    TIMESTAMP: 2026-02-18T15:30:00
    ```
    
    The lock is considered stale if:
    - Process with PID doesn't exist
    - Process exists but hostname doesn't match (distributed systems)
    """
    
    def __init__(self, run_dir: Path):
        """Initialize lock manager.
        
        Args:
            run_dir: Directory for benchmark run
        """
        self.run_dir = run_dir
        self.lock_file = run_dir / ".benchmark.lock"
        self.current_pid = os.getpid()
        self.current_hostname = socket.gethostname()
    
    def acquire(self, force: bool = False) -> bool:
        """Acquire lock for this process.
        
        Args:
            force: If True, break stale locks
            
        Returns:
            True if lock acquired successfully
            
        Raises:
            RuntimeError: If lock is held by another active process
        """
        from datetime import datetime
        
        # Check existing lock
        if self.lock_file.exists():
            existing_lock = self.read_lock()
            
            if existing_lock:
                # Check if process is alive
                if existing_lock.is_alive():
                    if force:
                        logger.warning(
                            f"Breaking active lock (PID {existing_lock.pid} on {existing_lock.hostname})"
                        )
                    else:
                        raise RuntimeError(
                            f"Benchmark is locked by PID {existing_lock.pid} on {existing_lock.hostname}. "
                            f"If you're sure no other process is running, use --force to break the lock."
                        )
                else:
                    logger.info(
                        f"Removing stale lock (PID {existing_lock.pid} on {existing_lock.hostname})"
                    )
                    self.release()
        
        # Create new lock
        timestamp = datetime.now().isoformat()
        lock_content = f"PID: {self.current_pid}\nHOSTNAME: {self.current_hostname}\nTIMESTAMP: {timestamp}\n"
        
        self.lock_file.write_text(lock_content)
        logger.debug(f"Lock acquired by PID {self.current_pid} on {self.current_hostname}")
        
        return True
    
    def release(self) -> None:
        """Release lock (delete lock file)."""
        if self.lock_file.exists():
            try:
                self.lock_file.unlink()
                logger.debug(f"Lock released by PID {self.current_pid}")
            except Exception as e:
                logger.warning(f"Failed to release lock: {e}")
    
    def read_lock(self) -> Optional[LockInfo]:
        """Read lock file information.
        
        Returns:
            Lock information if valid, None otherwise
        """
        if not self.lock_file.exists():
            return None
        
        try:
            content = self.lock_file.read_text()
            lines = content.strip().split("\n")
            
            info = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    info[key.strip()] = value.strip()
            
            if "PID" not in info or "HOSTNAME" not in info:
                logger.warning(f"Invalid lock file format: {self.lock_file}")
                return None
            
            return LockInfo(
                pid=int(info["PID"]),
                hostname=info["HOSTNAME"],
                timestamp=info.get("TIMESTAMP", "unknown"),
            )
        except Exception as e:
            logger.warning(f"Failed to read lock file: {e}")
            return None
    
    def is_locked(self, check_alive: bool = True) -> bool:
        """Check if benchmark is locked by another process.
        
        Args:
            check_alive: If True, consider stale locks as unlocked
            
        Returns:
            True if locked by active process
        """
        if not self.lock_file.exists():
            return False
        
        lock_info = self.read_lock()
        if not lock_info:
            return False
        
        # If it's our own lock
        if lock_info.pid == self.current_pid:
            return False
        
        # Check if process is alive
        if check_alive:
            return lock_info.is_alive()
        
        return True
    
    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


def detect_stale_scenarios(scenarios: dict) -> list:
    """Detect scenarios that were running but process died.
    
    Args:
        scenarios: Dict of scenario_id -> ScenarioResult
        
    Returns:
        List of stale scenario IDs
    """
    if not PSUTIL_AVAILABLE:
        logger.warning("psutil not available, cannot detect stale scenarios")
        return []
    
    from mas.lab.benchmark.metadata import ScenarioState
    
    stale = []
    
    for scenario_id, result in scenarios.items():
        if result.state == ScenarioState.RUNNING and result.process_pid:
            try:
                process = psutil.Process(result.process_pid)
                if not process.is_running():
                    stale.append(scenario_id)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                stale.append(scenario_id)
    
    return stale
