#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures — controller daemon for functional / tutorial tests."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

# Isolate controller paths before any mas.lab.controller import at collection time.
_TEST_HOME = Path(tempfile.mkdtemp(prefix="mas-test-home-"))
_CONTROLLER_DIR = _TEST_HOME / "controller"
_CONTROLLER_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MAS_HOME"] = str(_TEST_HOME)
os.environ["MAS_CONTROLLER_DIR"] = str(_CONTROLLER_DIR)
os.environ["MAS_CONTROLLER_SOCKET"] = str(_TEST_HOME / "controller.sock")
os.environ["MAS_CONTROLLER_PID"] = str(_CONTROLLER_DIR / "controller.pid")
os.environ["MAS_CONTROLLER_LOG"] = str(_CONTROLLER_DIR / "daemon.log")
os.environ.setdefault("MAS_CONTROLLER_NO_HTTP", "1")
os.environ.setdefault("MAS_CONTROLLER_IDLE_SEC", "120")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_WORKSPACE = _REPO_ROOT / "examples" / "sample-workspace"
if _SAMPLE_WORKSPACE.is_dir():
    # Force sample workspace — parent checkouts may export MAS_WORKSPACE_ROOT with
    # integration-only infra_refs (e.g. team:llm-proxy).
    os.environ["MAS_WORKSPACE_ROOT"] = str(_SAMPLE_WORKSPACE)

_XDG_CONFIG = _TEST_HOME / "xdg-config"
_XDG_DATA = _TEST_HOME / "xdg-data"
_XDG_CACHE = _TEST_HOME / "xdg-cache"
_XDG_STATE = _TEST_HOME / "xdg-state"
for _d in (_XDG_CONFIG, _XDG_DATA, _XDG_CACHE, _XDG_STATE):
    _d.mkdir(parents=True, exist_ok=True)
(_XDG_CONFIG / "mas").mkdir(parents=True, exist_ok=True)
os.environ["XDG_CONFIG_HOME"] = str(_XDG_CONFIG)
os.environ["XDG_DATA_HOME"] = str(_XDG_DATA)
os.environ["XDG_CACHE_HOME"] = str(_XDG_CACHE)
os.environ["XDG_STATE_HOME"] = str(_XDG_STATE)


@pytest.fixture(scope="session")
def mas_controller_home() -> Path:
    """Isolated MAS_HOME for the test session (daemon socket + pid)."""
    yield _TEST_HOME


@pytest.fixture(scope="session", autouse=True)
def mas_controller_daemon(request: pytest.FixtureRequest, mas_controller_home: Path) -> None:
    """Auto-start controller daemon once per pytest session; idle-shutdown after tests."""
    # Tutorial scenario/command tests shell out to CLIs and do not need the daemon.
    try:
        items = request.session.items
    except AttributeError:
        items = []
    if items and all(
        "tests/tutorials" in str(item.path)
        or "test_apply_license_headers" in str(item.path)
        for item in items
    ):
        yield
        return

    from mas.lab.controller.client import ControllerClient, start_daemon

    client = ControllerClient()
    if not client.is_running():
        start_daemon(detach=True)
        for _ in range(60):
            if client.is_running():
                break
            time.sleep(0.25)
        else:
            log = mas_controller_home / "controller" / "daemon.log"
            hint = log.read_text(encoding="utf-8")[-2000:] if log.is_file() else ""
            pytest.fail(f"Controller daemon failed to start\n{hint}")

    client.ensure_running(auto_start=False)
    yield
    from mas.lab.controller.client import _release_process_session

    _release_process_session()
