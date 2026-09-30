from __future__ import annotations

from collections.abc import Callable

from mas.runtime.boundary.agentcomm.protocol import AgentCommContract

RunTurnFn = Callable[[str, str, int, str, str], str]


class LocalAgentComm(AgentCommContract):
    """Agent communication over the current in-process workflow bus."""

    def __init__(self, run_turn: RunTurnFn) -> None:
        self._run_turn = run_turn

    def close(self) -> None:
        return None

    def send(
        self,
        target_agent_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
        context_id: str = "",
    ) -> str:
        return self._run_turn(
            target_agent_id,
            task,
            correlation_id,
            caller_call_id,
            context_id,
        )