#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine contract — Mealy hook for Layer-C execution (LLM, tools, memory, transport)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


@runtime_checkable
class EngineContract(Protocol):
    """Invoke engine I/O requested by kernel egress (M_model / M_tool)."""

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn: ...


@runtime_checkable
class CompactionSummarizeEngine(Protocol):
    """Out-of-band summarization for commit-time / view-time context compaction."""

    def summarize_messages(self, messages: list[dict[str, Any]]) -> str: ...
