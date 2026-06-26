#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared tutorial tool execution (mock + live engine tool loop)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mas.runtime.driver.mocks import AutoCtxAssembler


def apple_is_fruit(ctx: AutoCtxAssembler | None, user: str) -> bool:
    if ctx is None:
        return False
    if ctx.apple_topic == "fruit":
        return True
    if ctx.apple_topic == "company":
        return False
    for _key, content in ctx.memory_seeds:
        if "fruit" in content.lower():
            return True
    return bool(
        re.search(r"\bfruit\b", user, re.I) and re.search(r"apple|meant|not the company", user, re.I)
    )


def apple_price_reply(*, fruit: bool) -> str:
    if fruit:
        return (
            "Based on current market data, fresh apples are approximately "
            "$1.50–$2.00 per pound at local grocery stores."
        )
    return (
        "Apple Inc. (AAPL) is trading around $190 on the NASDAQ. "
        "Would you like a more detailed quote?"
    )


def execute_tutorial_tool(
    tool: str,
    *,
    ctx: AutoCtxAssembler | None,
    user: str,
    arguments: dict | None = None,
) -> str:
    try:
        from mas.library.standard.tools import execute_tool

        out = execute_tool(tool, arguments=arguments, user=user, ctx=ctx)
        if out is not None:
            return out
    except ImportError:
        pass

    fruit = apple_is_fruit(ctx, user)
    if tool == "calculator":
        return "[calculator] 65536"
    if tool == "verify_fact" or "apple" in user.lower():
        return apple_price_reply(fruit=fruit)
    return f"[{tool}] verified"
