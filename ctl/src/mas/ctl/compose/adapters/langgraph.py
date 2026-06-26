#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LangGraph framework adapter — wraps native RuntimeInstance (requires langgraph)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mas.ctl.compose.models import EffectiveBindManifest, FrameworkAdapterId
from mas.runtime.driver.instance import RuntimeInstance


@dataclass
class LangGraphHandle:
    """Runnable handle backed by a compiled LangGraph StateGraph."""

    agent_id: str
    instance: RuntimeInstance
    bind: EffectiveBindManifest
    graph: Any = field(default=None, repr=False)

    def invoke(self, user_text: str) -> str:
        if self.graph is not None:
            result = self.graph.invoke({"user_text": user_text})
            if isinstance(result, dict) and result.get("response"):
                return str(result["response"])
        from mas.runtime.driver.driver import KernelDriver
        from mas.runtime.schema.ingress import UserInputReceived

        driver = KernelDriver(self.instance)
        trace = driver.run([UserInputReceived(user_turn_id="u1", text=user_text)])
        if trace.final_response:
            return trace.final_response
        return trace.exchanges[-1].text if trace.exchanges else ""


class LangGraphFrameworkAdapter:
    """Wrap RuntimeInstance in a LangGraph StateGraph."""

    adapter_id: FrameworkAdapterId = "langgraph"

    def wrap(
        self, instance: RuntimeInstance, bind: EffectiveBindManifest, agent_id: str
    ) -> LangGraphHandle:
        graph = self._build_graph(instance, agent_id, bind)
        return LangGraphHandle(agent_id=agent_id, instance=instance, bind=bind, graph=graph)

    def _build_graph(
        self, instance: RuntimeInstance, agent_id: str, bind: EffectiveBindManifest
    ) -> Any:
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as exc:
            raise ImportError(
                "langgraph is required when framework_adapter is 'langgraph'. "
                "Install with: pip install langgraph"
            ) from exc

        from typing import TypedDict

        class AgentState(TypedDict, total=False):
            user_text: str
            response: str

        def run_kernel(state: AgentState) -> AgentState:
            text = state.get("user_text", "")
            handle = LangGraphHandle(
                agent_id=agent_id, instance=instance, bind=bind, graph=None
            )
            return {"response": handle.invoke(text)}

        g = StateGraph(AgentState)
        g.add_node("kernel", run_kernel)
        g.set_entry_point("kernel")
        g.add_edge("kernel", END)
        return g.compile()
