#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine contract — Mealy hook for Layer-C execution (LLM, tools, memory, transport)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


@runtime_checkable
class EngineContract(Protocol):
    """Invoke engine I/O requested by kernel egress (M_model / M_tool)."""

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn: ...
