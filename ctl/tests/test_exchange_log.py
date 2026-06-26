#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Exchange trace formatting."""

from __future__ import annotations

from mas.ctl.session.exchange_log import format_exchange
from mas.ctl.session.exchange_log import TraceFormatOptions
from mas.runtime.driver.driver import ExchangeRecord


def test_format_exchange_timestamps():
    ex = ExchangeRecord(
        tag="AGENT->LLM",
        text="[user]\n  hello",
        detail="correlation_id=1 op=LLM_CALL",
        ts_mono=1.5,
        ts_wall="2026-06-17T12:00:00.000Z",
    )
    out = format_exchange(
        "agent",
        ex,
        fmt=TraceFormatOptions(timestamps=True, turn_start_mono=1.0),
    )
    assert "2026-06-17T12:00:00.000Z" in out
    assert "(+0.500s)" in out


def test_format_exchange_engine_io():
    ex = ExchangeRecord(
        tag="LLM->AGENT",
        text="content:\n  hi",
        detail="correlation_id=1 response_kind=MODEL_TEXT",
        engine_raw='{"next_step": "STOP", "text": "hi"}',
    )
    out = format_exchange("agent", ex, fmt=TraceFormatOptions(engine_io=True))
    assert "engine:" in out
    assert "next_step" in out
