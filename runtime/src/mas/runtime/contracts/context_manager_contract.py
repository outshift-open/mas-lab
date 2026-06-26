#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ContextManagerContract — conversation-history strategies for M_ctx."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextManagerContract(ABC):
    """Trim or compress past user/assistant turns before each LLM call."""

    @abstractmethod
    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        """Return a possibly shorter version of *past* (excludes current user turn)."""
