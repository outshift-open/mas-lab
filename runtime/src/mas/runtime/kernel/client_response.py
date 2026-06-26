#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Build client-facing responses from run ledger state."""

from __future__ import annotations

from mas.runtime.kernel.response_text import response_text_from_run
from mas.runtime.schema.egress import EmitClientResponse
from mas.runtime.kernel.state import RunLedger


def client_response_from_run(
    run: RunLedger,
    *,
    fallback: str = "I could not produce a response.",
) -> EmitClientResponse:
    """Emit ``finish_reason=error`` when the last run event is an engine ERROR."""
    content = response_text_from_run(run, fallback=fallback)
    finish: str = "stop"
    if run.events and run.events[-1].response_kind == "ERROR":
        finish = "error"
    return EmitClientResponse(content=content, finish_reason=finish)  # type: ignore[arg-type]
