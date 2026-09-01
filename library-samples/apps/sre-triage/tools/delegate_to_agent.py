"""A2A delegation tool — routes a task to a specialist agent via the local bus.

This tool allows the entry agent (SRE orchestrator) to programmatically invoke
specialist agents (telemetry, backend, db, comms, verifier) and collect their
responses before synthesizing a final triage report.

Usage by the LLM (ReAct protocol):
    {
      "type": "tool",
      "tool_name": "delegate_to_agent",
      "arguments": {
        "agent_id": "telemetry",
        "task": "Analyse latency metrics for the payment service over the last 30 minutes."
      }
    }
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from mas.runtime.contracts import ToolContract

logger = logging.getLogger(__name__)


class DelegateToAgentTool(ToolContract):
    """Delegate a task to a specialist agent via the A2A local bus."""

    # ------------------------------------------------------------------
    # Lifecycle — called once by the runtime when the agent is wired up
    # ------------------------------------------------------------------

    def attach_agent(self, agent: Any) -> None:
        super().attach_agent(agent)
        self._a2a_bus = getattr(agent, "a2a_bus", None)

    # ------------------------------------------------------------------
    # Plugin interface (canonical pattern — mirrors DelegateTaskTool)
    # ------------------------------------------------------------------

    def on_collect_tools(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "name": "delegate_to_agent",
                "description": (
                    "Delegate an investigation or analysis task to a specialist agent. "
                    "Available agents: telemetry (metrics/logs/traces), backend (API/service health), "
                    "db (database performance), comms (stakeholder notifications), "
                    "verifier (validate findings and action plans)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "enum": ["telemetry", "backend", "db", "comms", "verifier"],
                            "description": "ID of the specialist agent to delegate to.",
                        },
                        "task": {
                            "type": "string",
                            "description": "Task description / question for the specialist agent.",
                        },
                    },
                    "required": ["agent_id", "task"],
                },
                "tool_category": "workflow_transition",
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "delegate_to_agent":
            return None

        # Accept both agent_id and agent_name (LLMs sometimes use the latter)
        agent_id: str = str(
            arguments.get("agent_id") or arguments.get("agent_name") or ""
        ).strip()
        task: str = str(arguments.get("task") or "").strip()

        if not agent_id or not task:
            return {
                "status": "error",
                "tool": tool_name,
                "data": {},
                "error": "agent_id and task are required",
            }

        if not self._a2a_bus:
            logger.warning("[delegate_to_agent] No A2A bus available — returning stub response")
            return {
                "status": "stub",
                "tool": tool_name,
                "data": {"agent_id": agent_id, "message": f"[stub] {agent_id} agent would analyse: {task}"},
            }

        if agent_id not in getattr(self._a2a_bus, "agents", {}):
            return {
                "status": "error",
                "tool": tool_name,
                "data": {},
                "error": (
                    f"Agent '{agent_id}' not found. "
                    f"Available: {list(getattr(self._a2a_bus, 'agents', {}).keys())}"
                ),
            }

        logger.info("[delegate_to_agent] %s → %s: %s…", self.agent_id, agent_id, task[:80])

        task_payload: Dict[str, Any] = {"prompt": task}
        correlation_id = str(uuid.uuid4())
        comm_data: Dict[str, Any] = {
            "source_agent_id": self.agent_id,
            "target_agent_id": agent_id,
            "message_type": "delegation",
            "task": task_payload,
            "correlation_id": correlation_id,
            "context": {},
        }

        # pre_agent_communication — enriches comm_data with parent_exec_call_id
        if self.agent is not None:
            self.agent.plugins.execute_hooks("pre_agent_communication", comm_data)

        parent_exec_call_id = comm_data.get("parent_exec_call_id")
        if parent_exec_call_id:
            task_payload["_tracing"] = {"parent_exec_call_id": parent_exec_call_id}

        result = self._a2a_bus.send(agent_id, task_payload)

        if self.agent is not None:
            self.agent.plugins.execute_hooks("post_agent_communication", {
                "source_agent_id": self.agent_id,
                "target_agent_id": agent_id,
                "message_type": "delegation",
                "correlation_id": correlation_id,
                "status": "success",
                "result": result,
            })

        return {"status": "ok", "tool": tool_name, "data": {"agent_id": agent_id, "result": result}}

    # ------------------------------------------------------------------
    # Legacy interface delegators (keep for backward compatibility)
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by DelegateToAgentTool")
        return result
