#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Native observability plugin — emits context_assembled and hook events."""

from __future__ import annotations

import time
from typing import Any

from mas.runtime.contracts.base import BasePlugin


class NativeObservabilityPlugin(BasePlugin):
    """Minimal observability for hook-plane tests and ctl trace."""

    contract_id = "recorder"

    def __init__(self, recorder: Any) -> None:
        super().__init__()
        self._recorder = recorder

    def attach_agent(self, agent: Any) -> None:
        super().attach_agent(agent)
        self.agent_id = getattr(agent, "agent_id", "unknown")

    def _emit(self, event: dict[str, Any]) -> None:
        if self._recorder is not None and hasattr(self._recorder, "emit"):
            self._recorder.emit(event)

    def on_pre_llm_call(self, data: dict[str, Any] | None = None, **_: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return data
        segments = data.pop("_context_segments", None)
        data.pop("_evicted_parts", None)
        data.pop("_summarized_turns", None)
        data.pop("_compaction_metadata", None)
        if segments is not None:
            self._emit(
                {
                    "kind": "context_assembled",
                    "agent_id": getattr(self, "agent_id", "unknown"),
                    "timestamp": time.time(),
                    "segments": segments,
                    "total_tokens": sum(s.get("tokens") or 0 for s in segments),
                    "segment_count": len(segments),
                }
            )
        return data
