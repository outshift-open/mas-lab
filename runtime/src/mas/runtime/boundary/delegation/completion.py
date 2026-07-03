#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation output parsing helpers."""

from __future__ import annotations

import re

_VERIFICATION_LINE = re.compile(
    r"VERIFICATION:\s*(APPROVED|FLAGGED|REJECTED)\b",
    re.IGNORECASE | re.MULTILINE,
)


def verification_status(text: str) -> str | None:
    match = _VERIFICATION_LINE.search(text)
    if not match:
        return None
    return match.group(1).upper()
