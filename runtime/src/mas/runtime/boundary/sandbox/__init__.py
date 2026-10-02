#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Sandbox around envelope execute — the body of ALLOW, not a new σ.

Governance ALLOW is a verdict. Adapters wrap ``execute_engine_tool``.
The kernel owns the protocol and the no-op. Workdir / bubblewrap /
landlock plugins register as ``type: execute_sandbox``.
"""

from __future__ import annotations

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
    """No isolation. Default when the spec omits a sandbox plugin."""

    name = "none"

    def run(self, fn: Callable[[], T], *, tool_name: str = "") -> T:
        return fn()

    async def arun(self, fn: Callable[[], Any], *, tool_name: str = "") -> Any:
        return await fn()


def sandbox_from_name(name: str, *, root: str | Path | None = None) -> ExecuteSandbox:
    """Resolve ``none`` locally; every other name is a library plugin."""
    key = (name or "none").strip().lower()
    if key in {"none", "passthrough", ""}:
        return PassthroughSandbox()
    from mas.runtime.registry import get_registry

    variant = get_registry().resolve_by_type("execute_sandbox", key)
    if variant is None:
        raise KeyError(f"unknown execute sandbox {name!r}")
    plugin_cls = variant.load_class()
    if root is None:
        return plugin_cls()
    return plugin_cls(root)
