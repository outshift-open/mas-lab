#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine tool loop — single dispatch: delegation plugin, registry tools, mock fallbacks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mas.runtime.boundary.delegation.protocol import DelegationContract


def execute_engine_tool(
    tool: str,
    *,
    delegation: DelegationContract | None = None,
    ctx: Any = None,
    user: str = "",
    arguments: dict[str, Any] | None = None,
) -> str:
    if delegation is not None and delegation.is_delegate_tool(tool):
        return delegation.call_delegate_tool(tool, arguments)
    return _execute_registered_or_mock_tool(tool, ctx=ctx, user=user, arguments=arguments)


def _execute_registered_or_mock_tool(
    tool: str,
    *,
    ctx: Any = None,
    user: str = "",
    arguments: dict[str, Any] | None = None,
) -> str:
    try:
        from mas.library.standard.tools import execute_tool

        out = execute_tool(tool, arguments=arguments, user=user, ctx=ctx)
        if out is not None:
            return out
    except ImportError:
        pass

    from mas.runtime.engine.mock_fixtures import apple_is_fruit, apple_price_reply

    fruit = apple_is_fruit(ctx, user)
    if tool == "calculator":
        return "[calculator] 65536"
    if tool == "verify_fact" or "apple" in user.lower():
        return apple_price_reply(fruit=fruit)
    return f"[{tool}] verified"
