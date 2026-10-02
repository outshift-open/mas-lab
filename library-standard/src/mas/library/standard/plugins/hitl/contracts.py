#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Default HITL / UserIO contract plugins (registry + unattended auto-resolve)."""

from __future__ import annotations

import threading
from typing import Any

from mas.runtime.boundary.hitl.registry import HitlResolverRegistry, get_hitl_resolver_registry
from mas.runtime.contracts.user_communication_contract import HITLContract, UserIOContract


def _resolve_registry(registry: HitlResolverRegistry | None) -> HitlResolverRegistry:
    if registry is not None:
        return registry
    return get_hitl_resolver_registry()


class RegistryHitlContract:
    """Register in HitlResolverRegistry and block until resolve() or timeout."""

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
                self._registry.resolve(
                    session_id, agent_id, correlation_id, choice="__timeout__", steering="timeout"
                )
            except KeyError:
                pass
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


class AutoResolveHitlContract:
    """HITLContract for unattended runs: answer immediately."""

    def __init__(self, decision: str = "approve") -> None:
        self.decision = decision

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
        return {
            "choice": self.decision,
            "steering": "",
            "question": question,
            "resolved": True,
        }


class RegistryUserIOContract:
    """Fire-and-forget user update on HitlResolverRegistry."""

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


# Protocols are runtime-owned; re-exported so callers can import one module.
__all__ = [
    "HITLContract",
    "UserIOContract",
    "RegistryHitlContract",
    "RegistryUserIOContract",
    "AutoResolveHitlContract",
]
