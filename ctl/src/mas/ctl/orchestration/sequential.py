#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Sequential workflow driver — TLA: CoordinationMachine.tla (future Extended product).

Deterministic DAG execution; no LLM routing at workflow level.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class WorkflowNode:
    id: str
    agent: str
    role: str = "specialist"


@dataclass
class WorkflowEdge:
    from_node: str
    to_node: str
    condition: str | None = None


@dataclass
class SequentialWorkflowSpec:
    entry: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge] = field(default_factory=list)


@dataclass
class SequentialWorkflowResult:
    content: str
    node_results: dict[str, str] = field(default_factory=dict)


def _topological_sort(node_ids: list[str], edges: list[WorkflowEdge]) -> list[str]:
    in_degree: dict[str, int] = {n: 0 for n in node_ids}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.from_node in in_degree and edge.to_node in in_degree:
            adjacency[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1
    queue = deque(n for n, deg in in_degree.items() if deg == 0)
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if len(order) != len(node_ids):
        raise ValueError("SequentialWorkflow: cycle detected in workflow graph")
    return order


class SequentialWorkflow:
    """Execute agents in topological order."""

    def __init__(
        self,
        spec: SequentialWorkflowSpec,
        *,
        send: Callable[[str, str], str],
    ) -> None:
        self.spec = spec
        self._send = send
        self._nodes = {n.id: n for n in spec.nodes}

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, send: Callable[[str, str], str]) -> SequentialWorkflow:
        nodes = [
            WorkflowNode(id=str(n["id"]), agent=str(n.get("agent") or n["id"]), role=str(n.get("role") or ""))
            for n in data.get("nodes") or []
        ]
        edges = [
            WorkflowEdge(
                from_node=str(e["from"]),
                to_node=str(e["to"]),
                condition=e.get("condition"),
            )
            for e in data.get("edges") or []
        ]
        return cls(
            SequentialWorkflowSpec(entry=str(data.get("entry") or nodes[0].id), nodes=nodes, edges=edges),
            send=send,
        )

    def run(self, task: str) -> SequentialWorkflowResult:
        order = _topological_sort(list(self._nodes.keys()), self.spec.edges)
        results: dict[str, str] = {}
        last = task
        for node_id in order:
            node = self._nodes[node_id]
            prompt = f"[workflow:{node_id}] {last}"
            last = self._send(node.agent, prompt)
            results[node_id] = last
        return SequentialWorkflowResult(content=last, node_results=results)
