#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Mock infrastructure adapters for simulated runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Any

from mas.runtime.boundary.context.dp_inject import inject_dp_protocol
from mas.runtime.boundary.context.working_memory import WorkingMemoryStore
from mas.runtime.schema.egress import RequestCtxAssembly
from mas.runtime.schema.ingress import CtxAssemblyComplete

if TYPE_CHECKING:
    from mas.runtime.kernel.state import QProduct


@dataclass
class AutoCtxAssembler:
    """Immediately complete context assembly on REQUEST_CTX_ASSEMBLY."""

    injected_context: list[str] = field(default_factory=list)
    memory_seeds: list[tuple[str, str]] = field(default_factory=list)
    last_user_text: str = ""
    turn_index: int = 0
    turn_history: list[tuple[str, str]] = field(default_factory=list)
    committed_messages: list[dict[str, Any]] = field(default_factory=list)
    working_memory: WorkingMemoryStore = field(default_factory=WorkingMemoryStore)
    apple_topic: str = "unset"  # unset | fruit | company
    pattern_plugin_id: str = "react@v1"
    runtime_params: dict[str, Any] = field(default_factory=dict)
    q_product: QProduct | None = None
    observability: Any | None = None
    _assembly_correlation_id: int = 0

    def capture_baseline(self) -> None:
        """Snapshot manifest-derived system context for /reset."""
        self._baseline_injected_context = list(self.injected_context)

    def reset_conversation(self) -> None:
        """Clear turn history and working memory; restore baseline system prompt."""
        baseline = getattr(self, "_baseline_injected_context", None)
        if baseline is not None:
            self.injected_context = list(baseline)
        self.turn_history.clear()
        self.committed_messages.clear()
        self.working_memory.clear()
        self.last_user_text = ""
        self.turn_index = 0
        self.apple_topic = "unset"
        self.runtime_params = {}
        from mas.runtime.boundary.context.telemetry import record_context_mutation

        record_context_mutation(
            self.observability,
            action="session_reset",
            committed_count=0,
            wm_count=0,
        )

    def note_user_input(self, text: str) -> None:
        from mas.runtime.boundary.context.telemetry import record_context_mutation

        record_context_mutation(
            self.observability,
            action="turn_start",
            turn_index=self.turn_index + 1,
            wm_count=len(self.working_memory.messages),
            committed_count=len(self.committed_messages),
        )
        self.last_user_text = text
        self.turn_index += 1
        self.working_memory.clear()
        record_context_mutation(
            self.observability,
            action="wm_clear",
            turn_index=self.turn_index,
            committed_count=len(self.committed_messages),
        )
        self._infer_topic_from_user(text)

    def note_agent_response(self, text: str) -> None:
        from mas.runtime.boundary.context.telemetry import record_context_mutation

        if self.last_user_text:
            self.committed_messages.append({"role": "user", "content": self.last_user_text})
            self.turn_history.append((self.last_user_text, text))
        if self.working_memory.messages:
            self.committed_messages.extend(self.working_memory.messages)
        if text.strip():
            last = self.committed_messages[-1] if self.committed_messages else {}
            if not (
                last.get("role") == "assistant"
                and str(last.get("content") or "").strip() == text.strip()
            ):
                self.committed_messages.append({"role": "assistant", "content": text})
        record_context_mutation(
            self.observability,
            action="turn_commit",
            turn_index=self.turn_index,
            content=text,
            committed_count=len(self.committed_messages),
            wm_count=len(self.working_memory.messages),
        )
        self.working_memory.clear()

    def record_assistant_tool_call(
        self,
        *,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        from mas.runtime.boundary.context.telemetry import record_context_mutation

        self.working_memory.record_assistant_tool_call(
            call_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        record_context_mutation(
            self.observability,
            action="wm_append",
            turn_index=self.turn_index,
            role="assistant",
            call_id=call_id,
            content=f"tool_call:{tool_name}",
            wm_count=len(self.working_memory.messages),
            committed_count=len(self.committed_messages),
        )

    def record_assistant_tool_calls(
        self,
        calls: list[tuple[str, str, dict[str, Any]]],
    ) -> None:
        self.working_memory.record_assistant_tool_calls(calls)

    def record_tool_result(self, *, call_id: str, content: str) -> None:
        from mas.runtime.boundary.context.telemetry import record_context_mutation

        self.working_memory.record_tool_result(call_id=call_id, content=content)
        record_context_mutation(
            self.observability,
            action="wm_append",
            turn_index=self.turn_index,
            role="tool",
            call_id=call_id,
            content=content,
            wm_count=len(self.working_memory.messages),
            committed_count=len(self.committed_messages),
        )

    def record_assistant_message(self, content: str) -> None:
        self.working_memory.record_assistant_message(content)

    def _infer_topic_from_user(self, text: str) -> None:
        t = text.lower()
        if any(p in t for p in ("meant the company", "the company", "not the fruit", "aapl", "stock price")):
            self.apple_topic = "company"
        elif any(p in t for p in ("meant the fruit", "the fruit", "not the company", "per pound", "grocery")):
            self.apple_topic = "fruit"

    def last_apple_question(self) -> str:
        for user_q, _ in reversed(self.turn_history):
            if "apple" in user_q.lower():
                return user_q
        if "apple" in self.last_user_text.lower():
            return self.last_user_text
        return ""

    def complete(self, request: RequestCtxAssembly) -> CtxAssemblyComplete:
        if request.operator_context:
            self.injected_context.append(request.operator_context)
        for key, content in self.memory_seeds:
            self.injected_context.append(f"[memory:{key}] {content}")
        self.injected_context = inject_dp_protocol(
            self.injected_context,
            pattern_plugin_id=self.pattern_plugin_id,
            q=self.q_product,
        )
        return CtxAssemblyComplete(collect_id=request.collect_id)
