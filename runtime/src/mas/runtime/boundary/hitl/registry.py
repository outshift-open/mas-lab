#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared HITL resolver registry for agent-initiated HITL across delegation boundaries."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from mas.runtime.schema.hitl import HitlQuestionType, HitlResolveChoice


@dataclass
class PendingHitlRequest:
    """A HITL request awaiting external resolution."""
    
    session_id: str
    agent_id: str
    correlation_id: int
    question: str
    question_type: HitlQuestionType
    choices: list[str]
    context_data: dict[str, Any]
    resolver_callback: Callable[[str, str], Any] | None = None  # (choice, steering) -> result


@dataclass
class PendingUserUpdate:
    """A fire-and-forget user-facing status message emitted by a system tool."""

    session_id: str
    agent_id: str
    correlation_id: int
    message: str
    user_name: str = ""
    involved_agents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class HitlResolverRegistry:
    """Thread-safe registry for pending HITL requests across agents/sessions.
    
    This registry enables agent-initiated HITL to work across delegation boundaries:
    1. Agent calls request_human_input tool
    2. Tool emits RequestHitlSignal
    3. Signal is caught and registered here
    4. External system (Webex bot) polls pending requests
    5. User responds via UI
    6. External system calls resolve() with user's choice
    7. Callback resumes agent's turn
    
    Thread-safe for concurrent MAS execution.
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        # pending[(session_id, agent_id, correlation_id)] = PendingHitlRequest
        self._pending: dict[tuple[str, str, int], PendingHitlRequest] = {}
        self._user_updates: dict[tuple[str, str, int], PendingUserUpdate] = {}
    
    def register(
        self,
        *,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        question: str,
        question_type: HitlQuestionType,
        choices: list[str],
        context_data: dict[str, Any],
        resolver_callback: Callable[[str, str], Any] | None = None,
    ) -> None:
        """Register a pending HITL request."""
        with self._lock:
            key = (session_id, agent_id, correlation_id)
            self._pending[key] = PendingHitlRequest(
                session_id=session_id,
                agent_id=agent_id,
                correlation_id=correlation_id,
                question=question,
                question_type=question_type,
                choices=list(choices),
                context_data=dict(context_data),
                resolver_callback=resolver_callback,
            )

    def register_user_update(
        self,
        *,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        message: str,
        user_name: str = "",
        involved_agents: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a non-blocking user update emitted from a delegating agent."""
        with self._lock:
            key = (session_id, agent_id, correlation_id)
            self._user_updates[key] = PendingUserUpdate(
                session_id=session_id,
                agent_id=agent_id,
                correlation_id=correlation_id,
                message=message,
                user_name=user_name,
                involved_agents=list(involved_agents or []),
                metadata=dict(metadata or {}),
            )
    
    def resolve(
        self,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        *,
        choice: str,
        steering: str = "",
    ) -> Any:
        """Resolve a pending HITL request with user's choice.
        
        Returns:
            The result from the resolver callback, if any.
        
        Raises:
            KeyError: If no pending request found for this key.
        """
        with self._lock:
            key = (session_id, agent_id, correlation_id)
            request = self._pending.pop(key, None)
            if request is None:
                raise KeyError(
                    f"No pending HITL request for session={session_id}, "
                    f"agent={agent_id}, correlation_id={correlation_id}"
                )
            if request.resolver_callback is None:
                return None
            return request.resolver_callback(choice, steering)
    
    def get_pending_for_session(self, session_id: str) -> dict[str, list[PendingHitlRequest]]:
        """Get all pending HITL requests for a session, grouped by agent_id.
        
        Returns:
            Dict mapping agent_id to list of pending requests.
        """
        with self._lock:
            result: dict[str, list[PendingHitlRequest]] = {}
            for (sid, aid, _), req in self._pending.items():
                if sid == session_id:
                    result.setdefault(aid, []).append(req)
            return result

    def get_pending_user_updates_for_session(self, session_id: str) -> dict[str, list[PendingUserUpdate]]:
        """Get all fire-and-forget user updates for a session, grouped by agent_id."""
        with self._lock:
            result: dict[str, list[PendingUserUpdate]] = {}
            for (sid, aid, _), req in self._user_updates.items():
                if sid == session_id:
                    result.setdefault(aid, []).append(req)
            return result
    
    def get_pending(
        self, session_id: str, agent_id: str, correlation_id: int | None = None
    ) -> list[PendingHitlRequest]:
        """Get pending HITL requests for a specific agent.
        
        Args:
            session_id: Session ID
            agent_id: Agent ID
            correlation_id: Optional correlation ID to filter by
        
        Returns:
            List of matching pending requests.
        """
        with self._lock:
            if correlation_id is not None:
                key = (session_id, agent_id, correlation_id)
                req = self._pending.get(key)
                return [req] if req else []
            
            result: list[PendingHitlRequest] = []
            for (sid, aid, _), req in self._pending.items():
                if sid == session_id and aid == agent_id:
                    result.append(req)
            return result
    
    def has_pending(self, session_id: str, agent_id: str | None = None) -> bool:
        """Check if there are any pending HITL requests.
        
        Args:
            session_id: Session ID
            agent_id: Optional agent ID filter
        
        Returns:
            True if any pending requests match the filter.
        """
        with self._lock:
            for (sid, aid, _) in self._pending:
                if sid == session_id:
                    if agent_id is None or aid == agent_id:
                        return True
            return False
    
    def clear_session(self, session_id: str) -> None:
        """Clear all pending HITL requests for a session."""
        with self._lock:
            to_remove = [k for k in self._pending if k[0] == session_id]
            for k in to_remove:
                del self._pending[k]
            for k in [key for key in self._user_updates if key[0] == session_id]:
                del self._user_updates[k]


# Global singleton registry
_HITL_RESOLVER_REGISTRY: HitlResolverRegistry | None = None
_REGISTRY_LOCK = threading.Lock()


def get_hitl_resolver_registry() -> HitlResolverRegistry:
    """Get the global HITL resolver registry singleton."""
    global _HITL_RESOLVER_REGISTRY
    if _HITL_RESOLVER_REGISTRY is None:
        with _REGISTRY_LOCK:
            if _HITL_RESOLVER_REGISTRY is None:
                _HITL_RESOLVER_REGISTRY = HitlResolverRegistry()
    return _HITL_RESOLVER_REGISTRY
