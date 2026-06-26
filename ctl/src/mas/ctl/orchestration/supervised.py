#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Supervised workflow — external operator loop between agent steps (release 2026.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from mas.ctl.orchestration.sequential import SequentialWorkflow


@dataclass
class SupervisedWorkflowResult:
    content: str
    node_results: dict[str, str] = field(default_factory=dict)
    approvals: list[str] = field(default_factory=list)


class SupervisedWorkflow(SequentialWorkflow):
    """Sequential workflow with operator approval between nodes."""

    plugin_id = "workflow-supervised@v1"

    def __init__(
        self,
        spec,
        *,
        send: Callable[[str, str], str],
        approve: Callable[[str, str], bool] | None = None,
    ) -> None:
        super().__init__(spec, send=send)
        self._approve = approve or (lambda _node, _preview: True)

    def run(self, task: str) -> SupervisedWorkflowResult:
        from mas.ctl.orchestration.sequential import _topological_sort

        order = _topological_sort(list(self._nodes.keys()), self.spec.edges)
        results: dict[str, str] = {}
        approvals: list[str] = []
        last = task
        for node_id in order:
            node = self._nodes[node_id]
            preview = f"Run agent '{node.agent}' for node '{node_id}'?"
            if not self._approve(node_id, preview):
                approvals.append(f"blocked:{node_id}")
                break
            approvals.append(f"approved:{node_id}")
            prompt = f"[supervised:{node_id}] {last}"
            last = self._send(node.agent, prompt)
            results[node_id] = last
        return SupervisedWorkflowResult(content=last, node_results=results, approvals=approvals)
