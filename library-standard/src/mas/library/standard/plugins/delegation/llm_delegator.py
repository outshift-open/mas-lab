#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Default delegation plugin — ``delegate_to_*`` over an injected AgentCommContract."""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.agentcomm.protocol import AgentCommContract, AgentCommError, set_current_transport
from mas.runtime.boundary.agentcomm.routing import AgentCommRoute


class LlmDelegator:
    """``DelegationContract`` over a supplied comm plugin; routes override per peer."""

    def __init__(
        self,
        *,
        comm: AgentCommContract,
        routes: dict[str, AgentCommRoute] | None = None,
    ) -> None:
        self._comm = comm
        self._routes = dict(routes or {})

    def set_routes(self, routes: dict[str, AgentCommRoute]) -> None:
        self._routes = dict(routes)

    def reset_session(self) -> None:
        """Compatibility hook retained for lifecycle callers; no cache persists."""
        return None

    def is_delegate_tool(self, tool_name: str) -> bool:
        from mas.runtime.boundary.delegation.policy import DELEGATE_TOOL_PREFIX

        return tool_name.startswith(DELEGATE_TOOL_PREFIX) and len(tool_name) > len(
            DELEGATE_TOOL_PREFIX
        )

    def _channel(self, target_agent_id: str) -> tuple[AgentCommContract, str]:
        route = self._routes.get(target_agent_id)
        if route is not None:
            return route.handler, route.kind
        return self._comm, "local-bus"

    def delegate(
        self,
        target_agent_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
        context_id: str = "",
    ) -> str:
        if not target_agent_id:
            return "[delegation] missing target agent id"
        task_key = task.strip()
        communication, protocol = self._channel(target_agent_id)
        set_current_transport(protocol)
        try:
            result = communication.send(
                target_agent_id,
                task_key,
                correlation_id=correlation_id,
                caller_call_id=caller_call_id,
                context_id=context_id,
            )
        except AgentCommError as exc:
            return f"[delegation] agent {target_agent_id!r} via {protocol} failed: {exc}"
        except KeyError:
            return f"[delegation] agent {target_agent_id!r} not available on bus"
        except RuntimeError as exc:
            return f"[delegation] agent {target_agent_id!r} failed: {exc}"

        return result

    def call_delegate_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        from mas.runtime.boundary.delegation.policy import parse_delegate_tool_name

        target = parse_delegate_tool_name(tool_name)
        if not target:
            return f"[delegation] not a delegate tool: {tool_name!r}"
        task = str((arguments or {}).get("task") or "").strip()
        if not task:
            return f"[delegation] missing task for {target!r}"
        context_id = str((arguments or {}).get("context_id") or "").strip()
        return self.delegate(
            target,
            task,
            correlation_id=correlation_id,
            caller_call_id=caller_call_id,
            context_id=context_id,
        )

    async def adelegate(
        self,
        target_agent_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
        context_id: str = "",
    ) -> str:
        if not target_agent_id:
            return "[delegation] missing target agent id"
        task_key = task.strip()
        communication, protocol = self._channel(target_agent_id)
        set_current_transport(protocol)
        try:
            asend = getattr(communication, "asend", None)
            if callable(asend):
                result = await asend(
                    target_agent_id,
                    task_key,
                    correlation_id=correlation_id,
                    caller_call_id=caller_call_id,
                    context_id=context_id,
                )
            else:
                result = communication.send(
                    target_agent_id,
                    task_key,
                    correlation_id=correlation_id,
                    caller_call_id=caller_call_id,
                    context_id=context_id,
                )
        except AgentCommError as exc:
            return f"[delegation] agent {target_agent_id!r} via {protocol} failed: {exc}"
        except KeyError:
            return f"[delegation] agent {target_agent_id!r} not available on bus"
        except RuntimeError as exc:
            return f"[delegation] agent {target_agent_id!r} failed: {exc}"

        return result

    async def acall_delegate_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        from mas.runtime.boundary.delegation.policy import parse_delegate_tool_name

        target = parse_delegate_tool_name(tool_name)
        if not target:
            return f"[delegation] not a delegate tool: {tool_name!r}"
        task = str((arguments or {}).get("task") or "").strip()
        if not task:
            return f"[delegation] missing task for {target!r}"
        context_id = str((arguments or {}).get("context_id") or "").strip()
        return await self.adelegate(
            target,
            task,
            correlation_id=correlation_id,
            caller_call_id=caller_call_id,
            context_id=context_id,
        )
