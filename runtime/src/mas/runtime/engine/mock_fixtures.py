#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Mock-engine fixtures for tutorial demos (apple price disambiguation)."""

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
