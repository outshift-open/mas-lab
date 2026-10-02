#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Sandbox around envelope execute — the body of ALLOW, not a new σ.

Governance ALLOW is a verdict. Without a sandbox the tool still has the
host. Adapters wrap ``execute_engine_tool``; they do not add envelope
symbols. OSS: workdir isolation here; bubblewrap/landlock/sandbox-exec
plug the same protocol.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class ExecuteSandbox(Protocol):
    """Run a tool body after authorize. Must not skip the envelope."""

    name: str

    def run(self, fn: Callable[[], T], *, tool_name: str = "") -> T: ...

    async def arun(self, fn: Callable[[], Any], *, tool_name: str = "") -> Any: ...


class PassthroughSandbox:
    """No isolation. Chat tools that cannot touch a filesystem."""

    name = "none"

    def run(self, fn: Callable[[], T], *, tool_name: str = "") -> T:
        return fn()

    async def arun(self, fn: Callable[[], Any], *, tool_name: str = "") -> Any:
        return await fn()


class WorkdirSandbox:
    """Tools see ``root`` as cwd / ``MAS_EXECUTE_ROOT``. Host stays outside.

    FastClaw docker and Flue just-bash are other adapters of this protocol.
    """

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


def sandbox_from_name(name: str, *, root: str | Path | None = None) -> ExecuteSandbox:
    key = (name or "none").strip().lower()
    if key in {"none", "passthrough", ""}:
        return PassthroughSandbox()
    if key in {"workdir", "git_worktree"}:
        if root is None:
            raise ValueError("workdir sandbox requires root")
        return WorkdirSandbox(root)
    raise KeyError(f"unknown execute sandbox {name!r}")
