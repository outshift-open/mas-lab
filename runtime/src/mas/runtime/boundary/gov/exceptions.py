#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance policy exceptions."""

from __future__ import annotations


class PolicySkip(Exception):
    """Tool egress skipped — inject synthetic τ record instead of engine call."""

    def __init__(self, *, tool_name: str, reason: str, synthetic_result: dict | None = None) -> None:
        self.tool_name = tool_name
        self.reason = reason
        self.synthetic_result = synthetic_result or {
            "status": "skipped",
            "reason": reason,
        }
        super().__init__(reason)


class PolicyViolation(Exception):
    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        self.recoverable = recoverable
        super().__init__(message)
