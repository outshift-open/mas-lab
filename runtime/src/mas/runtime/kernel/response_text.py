#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Extract client-visible text from τ ledger after engine I/O."""

from __future__ import annotations

from mas.runtime.kernel.state import RunLedger


def response_text_from_run(run: RunLedger, *, fallback: str = "") -> str:
    """Return the latest model or tool result text from τ."""
    for rec in reversed(run.events):
        if rec.text.strip():
            return rec.text.strip()
    return fallback
