#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Graph workflow driver — heterogeneous topology (release 2026.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from mas.ctl.orchestration.sequential import SequentialWorkflow, SequentialWorkflowSpec, WorkflowEdge, WorkflowNode


@dataclass
class GraphWorkflowResult:
    content: str
    node_results: dict[str, str] = field(default_factory=dict)


class GraphWorkflow(SequentialWorkflow):
    """Graph execution — delegates to sequential topo sort for 2026.1."""

    plugin_id = "workflow-graph@v1"

    def run(self, task: str) -> GraphWorkflowResult:
        base = super().run(task)
        return GraphWorkflowResult(content=base.content, node_results=base.node_results)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, send: Callable[[str, str], str]) -> GraphWorkflow:
        seq = SequentialWorkflow.from_dict(data, send=send)
        return cls(seq.spec, send=send)
