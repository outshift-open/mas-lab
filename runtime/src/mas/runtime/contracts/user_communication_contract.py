#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HITLContract / UserIOContract — the seam between an agent's request_human_input()/
inform_user() calls and whatever surfaces them to a real human (a CLI prompt, a chat
UI card, an admin console, ...) and, for HITL, resumes the agent with the answer.

Mirrors HitlResponder (mas.runtime.boundary.hitl.responders) -- a plain Protocol, not
the deeper CapabilityContract/ContractRegistry taxonomy used for tool/memory/budget-style
internal capabilities. This is a user-facing interaction seam, not an internal resource
boundary.

Consumed by _SystemToolHitlWrapper / _SystemToolUserUpdateWrapper
(mas.runtime.engine.manifest_tool_provider), which construct a Registry*Contract by
default when no other implementation is supplied -- so every existing caller keeps its
current (registry-based) behavior unless it deliberately opts into something else.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol

from mas.runtime.boundary.hitl.registry import HitlResolverRegistry


def _resolve_registry(registry: HitlResolverRegistry | None) -> HitlResolverRegistry:
    if registry is not None:
        return registry
    from mas.runtime.boundary.hitl.registry import get_hitl_resolver_registry

    return get_hitl_resolver_registry()


class HITLContract(Protocol):
    """Ask a human a question and get their answer back, resuming the agent."""

    def request_approval(
        self,
        *,
        question: str,
        session_id: str,
        requesting_user_id: str,
        agent_id: str,
        correlation_id: int,
        question_type: str,
        choices: list[str],
        context_data: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return at least {"choice": <str>}; may also include "steering" (free text).

        `timeout` (seconds) is the caller's requested wait limit -- None means
        wait indefinitely. Implementations that can't meaningfully time out
        (e.g. a synchronous stdin prompt) may ignore it; a blocking
        implementation should raise TimeoutError if it elapses.
        """
        ...


class UserIOContract(Protocol):
    """Send a non-blocking progress update to whoever is watching the session."""

    def send_progress_update(
        self,
        *,
        message: str,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        requesting_user_id: str,
        involved_agents: list[str],
        metadata: dict[str, Any],
    ) -> Any:
        """Return value is an opaque receipt -- callers should not depend on its shape."""
        ...


class RegistryHitlContract:
    """The default HITLContract: register in HitlResolverRegistry and block until an
    external resolver (chat integration, admin console, ...) calls registry.resolve(), or until
    `timeout` elapses.

    This is exactly the registry-register-and-block behavior _SystemToolHitlWrapper used
    to run inline as its "no contract supplied" fallback -- moved here so that behavior is
    the default *implementation* of a real contract, not a hidden special case.
    """

    def __init__(self, registry: HitlResolverRegistry | None = None) -> None:
        self._registry = _resolve_registry(registry)

    def request_approval(
        self,
        *,
        question: str,
        session_id: str,
        requesting_user_id: str,
        agent_id: str,
        correlation_id: int,
        question_type: str,
        choices: list[str],
        context_data: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        from mas.runtime.schema.hitl import HitlQuestionType

        resolution_event = threading.Event()
        resolution_result: dict[str, str | None] = {"choice": None, "steering": None}

        def callback(choice: str, steering: str) -> dict[str, str]:
            """Callback invoked by external resolver (chat integration, admin console, ...)."""
            resolution_result["choice"] = choice
            resolution_result["steering"] = steering
            resolution_event.set()
            return {"status": "resolved", "choice": choice}

        self._registry.register(
            session_id=session_id,
            agent_id=agent_id,
            correlation_id=correlation_id,
            question=question,
            question_type=HitlQuestionType(question_type),
            choices=choices,
            context_data=context_data,
            resolver_callback=callback,
        )

        did_resolve = resolution_event.wait(timeout=timeout)

        if not did_resolve:
            try:
                self._registry.resolve(session_id, agent_id, correlation_id, choice="__timeout__", steering="timeout")
            except KeyError:
                pass  # Already resolved or cleaned up
            raise TimeoutError(
                f"HITL request timed out after {timeout}s "
                f"(session={session_id}, agent={agent_id}, correlation_id={correlation_id}): {question}"
            )

        return {
            "choice": resolution_result["choice"],
            "steering": resolution_result["steering"] or "",
            "question": question,
            "resolved": True,
        }


class RegistryUserIOContract:
    """The default UserIOContract: register a fire-and-forget entry in
    HitlResolverRegistry's user-update channel (e.g. polled by an external integration via
    get_pending_user_updates_for_session())."""

    def __init__(self, registry: HitlResolverRegistry | None = None) -> None:
        self._registry = _resolve_registry(registry)

    def send_progress_update(
        self,
        *,
        message: str,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        requesting_user_id: str,
        involved_agents: list[str],
        metadata: dict[str, Any],
    ) -> None:
        self._registry.register_user_update(
            session_id=session_id,
            agent_id=agent_id,
            correlation_id=correlation_id,
            message=message,
            user_name=requesting_user_id,
            involved_agents=involved_agents,
            metadata=metadata,
        )


__all__ = [
    "HITLContract",
    "UserIOContract",
    "RegistryHitlContract",
    "RegistryUserIOContract",
]
