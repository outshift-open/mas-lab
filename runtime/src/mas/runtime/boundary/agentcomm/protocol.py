from __future__ import annotations

from contextvars import ContextVar
from typing import Protocol, runtime_checkable

_current_transport: ContextVar[str] = ContextVar(
    "mas_agent_comm_transport",
    default="",
)


def set_current_transport(protocol: str) -> None:
    _current_transport.set(protocol)


def consume_current_transport() -> str:
    protocol = _current_transport.get()
    _current_transport.set("")
    return protocol


class AgentCommError(RuntimeError):
    """Raised when an agent communication plugin cannot complete a send."""


@runtime_checkable
class AgentCommContract(Protocol):
    """Send a task to a peer agent through a selected communication protocol."""

    def send(
        self,
        target_agent_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
        context_id: str = "",
    ) -> str: ...