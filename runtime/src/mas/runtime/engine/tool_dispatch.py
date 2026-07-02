#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine tool loop — delegation plugin and manifest tool provider dispatch."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mas.runtime.engine.manifest_tool_provider import ManifestToolLoadError

if TYPE_CHECKING:
    from mas.runtime.boundary.delegation.protocol import DelegationContract
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot be executed."""


def format_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return json.dumps(result, indent=2)
    return str(result)


def execute_engine_tool(
    tool: str,
    *,
    delegation: DelegationContract | None = None,
    ctx: Any = None,
    user: str = "",
    arguments: dict[str, Any] | None = None,
    tool_provider: ManifestToolProvider | None = None,
) -> str:
    if delegation is not None and delegation.is_delegate_tool(tool):
        return delegation.call_delegate_tool(tool, arguments)
    if tool_provider is None:
        raise ToolExecutionError(
            f"No manifest tool provider configured; cannot execute {tool!r}"
        )
    try:
        result = tool_provider.call_tool(
            tool,
            arguments or {},
            ctx=ctx,
            user=user,
        )
    except ManifestToolLoadError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return format_tool_result(result)
