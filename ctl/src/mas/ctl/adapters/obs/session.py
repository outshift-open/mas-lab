#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability session hooks — session-level native events."""

from __future__ import annotations

from dataclasses import dataclass

from mas.ctl.adapters.obs.pipeline import ObservabilityPipeline
from mas.runtime.driver.driver import DriverTrace


@dataclass
class SessionObservabilityRecorder:
    pipeline: ObservabilityPipeline

    def on_user_turn(self, text: str, *, turn_id: str) -> None:
        self.pipeline.context.turn_id = turn_id
        self.pipeline.ingest_session("user_input", text=text)

    def on_agent_turn(self, trace: DriverTrace, *, response_text: str) -> None:
        if response_text:
            self.pipeline.ingest_session(
                "agent_response",
                text=response_text,
                finish_reason="stop",
            )

    def close(self) -> None:
        self.pipeline.flush()
        self.pipeline.close()
