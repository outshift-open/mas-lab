#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Workdir execute-sandbox plugin — isolation around envelope execute."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class WorkdirSandbox:
    """Tools see ``root`` as cwd / ``MAS_EXECUTE_ROOT``. Host stays outside."""

    name = "workdir"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def run(self, fn: Callable[[], T], *, tool_name: str = "") -> T:
        previous = os.getcwd()
        previous_env = os.environ.get("MAS_EXECUTE_ROOT")
        os.chdir(self.root)
        os.environ["MAS_EXECUTE_ROOT"] = str(self.root)
        try:
            return fn()
        finally:
            os.chdir(previous)
            if previous_env is None:
                os.environ.pop("MAS_EXECUTE_ROOT", None)
            else:
                os.environ["MAS_EXECUTE_ROOT"] = previous_env

    async def arun(self, fn: Callable[[], Any], *, tool_name: str = "") -> Any:
        previous = os.getcwd()
        previous_env = os.environ.get("MAS_EXECUTE_ROOT")
        os.chdir(self.root)
        os.environ["MAS_EXECUTE_ROOT"] = str(self.root)
        try:
            return await fn()
        finally:
            os.chdir(previous)
            if previous_env is None:
                os.environ.pop("MAS_EXECUTE_ROOT", None)
            else:
                os.environ["MAS_EXECUTE_ROOT"] = previous_env
