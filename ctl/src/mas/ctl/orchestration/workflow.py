#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Multi-agent workflow driver (v2 ctl orchestration)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class WorkflowRunResult:
    content: str
    agent_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DynamicWorkflow:
    """Default workflow: deliver task to entry agent via in-process bus."""

    def __init__(
        self,
        *,
        entry_agent: str,
        send: Callable[[str, str], str],
    ) -> None:
        self.entry_agent = entry_agent
        self._send = send

    def run(self, task: str) -> WorkflowRunResult:
        text = self._send(self.entry_agent, task)
        return WorkflowRunResult(content=text, agent_id=self.entry_agent)


def build_dynamic_workflow(**kwargs: Any) -> DynamicWorkflow:
    return DynamicWorkflow(**kwargs)
