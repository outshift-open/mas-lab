#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Controller daemon paths and defaults."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HTTP_PORT = int(os.environ.get("MAS_CONTROLLER_PORT", "9000"))


def mas_dir() -> Path:
    return Path(os.environ.get("MAS_HOME", Path.home() / ".mas"))


def controller_dir() -> Path:
    return Path(os.environ.get("MAS_CONTROLLER_DIR", mas_dir() / "controller"))


def socket_path() -> Path:
    return Path(os.environ.get("MAS_CONTROLLER_SOCKET", mas_dir() / "controller.sock"))


def pid_path() -> Path:
    return Path(os.environ.get("MAS_CONTROLLER_PID", controller_dir() / "controller.pid"))


def ensure_mas_dirs() -> None:
    mas_dir().mkdir(parents=True, exist_ok=True)
    controller_dir().mkdir(parents=True, exist_ok=True)
