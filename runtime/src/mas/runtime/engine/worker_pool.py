#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-process engine I/O queue for one kernel dispatch batch."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn
from mas.runtime.spec.defaults import DEFAULT_ENGINE_QUEUE_DEPTH

WorkerFn = Callable[[InvokeEngineIo], EngineIoReturn]


@dataclass
class EngineWorkerPool:
    """Queue engine egress intents from one batch; drain runs invoke sequentially."""

    worker: WorkerFn
    outbound_queue: deque[InvokeEngineIo] = field(default_factory=deque)
    inbound_queue: deque[EngineIoReturn] = field(default_factory=deque)
    max_depth: int = DEFAULT_ENGINE_QUEUE_DEPTH

    def submit(self, intent: InvokeEngineIo) -> None:
        if len(self.outbound_queue) >= self.max_depth:
            raise RuntimeError("engine outbound queue full")
        self.outbound_queue.append(intent)

    def pending_outbound(self) -> int:
        return len(self.outbound_queue)

    def pending_inbound(self) -> int:
        return len(self.inbound_queue)

    def process_one(self) -> EngineIoReturn | None:
        if not self.outbound_queue:
            return None
        intent = self.outbound_queue.popleft()
        result = self.worker(intent)
        self.inbound_queue.append(result)
        return result

    def drain(self) -> list[EngineIoReturn]:
        results: list[EngineIoReturn] = []
        while self.outbound_queue:
            got = self.process_one()
            if got is not None:
                results.append(got)
        return results

    def pop_inbound(self) -> EngineIoReturn | None:
        if not self.inbound_queue:
            return None
        return self.inbound_queue.popleft()
