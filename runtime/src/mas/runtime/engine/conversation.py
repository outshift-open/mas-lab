#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Conversation engine — contextual mock responses for CLI and tutorials (no v1 LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mas.runtime.engine.simulated import SimMode, simulated_next_step
from mas.runtime.engine.mock_fixtures import apple_is_fruit, apple_price_reply
from mas.runtime.engine.tool_dispatch import execute_engine_tool
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn

if TYPE_CHECKING:
    from mas.runtime.driver.mocks import AutoCtxAssembler


def _has_fruit_preference(ctx: AutoCtxAssembler) -> bool:
    for _key, content in ctx.memory_seeds:
        if "fruit" in content.lower():
            return True
    for line in ctx.injected_context:
        if "fruit" in line.lower() and "memory" in line.lower():
            return True
    return False


def _capital_reply(user: str) -> str:
    if "france" in user.lower():
        return "The capital of France is Paris."
    return f"I understand you asked: {user[:200]}"


@dataclass
class ConversationEngine:
    """Default CLI engine: readable answers using user text and memory seeds."""

    ctx: AutoCtxAssembler | None = None
    sim_mode: SimMode = SimMode.DEFAULT
    use_tool_loop: bool = False
    delegation: Any | None = None
    _pending_tool: str = field(default="", init=False)
    _pending_tool_args: dict = field(default_factory=dict, init=False)

    def reset_turn_state(self) -> None:
        self._pending_tool = ""
        self._pending_tool_args = {}

    def exchange_preview(self, op: str) -> str:
        from mas.runtime.engine.exchange_preview import format_llm_messages, format_tool_invoke

        if op == "LLM_CALL":
            user = (self.ctx.last_user_text if self.ctx else "") or ""
            messages = [{"role": "user", "content": user}] if user else [{"role": "user", "content": "Hello"}]
            if self.ctx:
                system: list[str] = []
                for line in self.ctx.injected_context:
                    if line.strip():
                        system.append(line.strip())
                if system:
                    messages = [{"role": "system", "content": "\n\n".join(system)}] + messages
            return format_llm_messages(messages)
        if op == "TOOL_CALL":
            return format_tool_invoke(self._pending_tool or "tool", self._pending_tool_args)
        return ""

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if io.op == "LLM_CALL":
            return self._llm_call(io)
        if io.op == "TOOL_CALL":
            return self._tool_call(io)
        if io.op == "MEMORY_OP":
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text="Memory updated.",
            )
        if io.op == "TRANSPORT_MSG":
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TRANSPORT_ACK",
                next_step="STOP",
                text="Message delivered.",
            )
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="ERROR",
            next_step="STOP",
            text="Unsupported engine operation.",
        )

    def _llm_call(self, io: InvokeEngineIo) -> EngineIoReturn:
        user = (self.ctx.last_user_text if self.ctx else "") or ""
        fruit_pref = _has_fruit_preference(self.ctx) if self.ctx else False
        has_tool_results = bool(
            self.ctx
            and any(m.get("role") == "tool" for m in self.ctx.working_memory.messages)
        )

        if has_tool_results and self.use_tool_loop:
            text = self._compose_reply_after_tool(user)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text=text,
            )

        if self.use_tool_loop and re.search(r"\bapple\b", user, re.I) and re.search(
            r"price|cost|trading|stock", user, re.I
        ):
            next_step = "TOOL_CALL"
        elif self.use_tool_loop:
            next_step = simulated_next_step(self.sim_mode, io.correlation_id)
        else:
            next_step = "STOP"

        if next_step == "TOOL_CALL":
            user_l = user.lower()
            if re.search(r"\bapple\b", user_l) and re.search(
                r"price|cost|trading|stock", user_l
            ):
                tool = "verify_fact"
                args = {"query": user[:120]}
            elif re.search(
                r"calc|compute|\d+\s*[\+\-\*/%]|percent|square root|\*\*",
                user_l,
            ):
                tool = "calculator"
                m = re.search(r"([\d\s+\-*/().%]+)", user)
                expr = (m.group(1).strip() if m else "") or "2+2"
                args = {"expression": expr}
            else:
                tool = "web-search"
                args = {"query": user.strip()[:120] or "general knowledge"}
            self._pending_tool = tool
            self._pending_tool_args = dict(args)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="TOOL_CALL",
                tool_name=tool,
                tool_arguments=args,
                text="",
            )

        text = self._compose_reply(user, fruit_pref=fruit_pref)
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="MODEL_TEXT",
            next_step="STOP",
            text=text,
        )

    def _tool_call(self, io: InvokeEngineIo) -> EngineIoReturn:
        tool = self._pending_tool or "tool"
        user = (self.ctx.last_user_text if self.ctx else "") or ""
        args = dict(self._pending_tool_args or {})
        self._pending_tool = ""
        self._pending_tool_args = {}
        body = execute_engine_tool(
            tool,
            delegation=self.delegation,
            ctx=self.ctx,
            user=user,
            arguments=args,
        )
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="TOOL_RESULT",
            next_step="LLM_CALL" if self.use_tool_loop else "STOP",
            text=body,
        )

    def _compose_reply_after_tool(self, user: str) -> str:
        if not self.ctx:
            return self._compose_reply(user, fruit_pref=False)
        tool_text = " ".join(
            str(m.get("content") or "")
            for m in self.ctx.working_memory.messages
            if m.get("role") == "tool"
        )
        if tool_text.strip() and re.search(
            r"\bpotus\b|president of the united states|current president", user, re.I
        ):
            return tool_text.strip()[:500]
        if tool_text.strip():
            return (
                f"Based on the search results: {tool_text.strip()[:500]}"
            )
        return self._compose_reply(user, fruit_pref=_has_fruit_preference(self.ctx))

    def _apple_is_fruit(self, user: str) -> bool:
        return apple_is_fruit(self.ctx, user)

    def _compose_reply(self, user: str, *, fruit_pref: bool) -> str:
        if not user.strip():
            return "How can I help you?"
        user_l = user.lower()

        if re.search(r"did not answer|didn't answer|wrong answer|not answer", user_l):
            return self._retry_last_apple_answer()

        if self.ctx and self.ctx.apple_topic != "unset":
            if re.search(r"meant|company|fruit|clarif|answer|sorry", user_l) or not re.search(
                r"\bapple\b", user, re.I
            ):
                q = self.ctx.last_apple_question() or user
                if q or self.ctx.apple_topic != "unset":
                    return apple_price_reply(fruit=self.ctx.apple_topic == "fruit")

        if re.search(r"\bapple\b", user, re.I) and re.search(r"price|cost|trading|stock", user, re.I):
            fruit = fruit_pref if self.ctx is None or self.ctx.apple_topic == "unset" else self.ctx.apple_topic == "fruit"
            if self.ctx and self.ctx.apple_topic == "unset":
                self.ctx.apple_topic = "fruit" if fruit else "company"
            return apple_price_reply(fruit=fruit)

        if re.search(r"\bfruit\b", user, re.I) and re.search(r"apple|meant|not the company", user, re.I):
            if self.ctx:
                self.ctx.apple_topic = "fruit"
            return apple_price_reply(fruit=True)

        if re.search(r"capital of", user, re.I):
            return _capital_reply(user)

        if fruit_pref and re.search(r"\bapple\b", user, re.I):
            if self.ctx:
                self.ctx.apple_topic = "fruit"
            return apple_price_reply(fruit=True)

        return (
            f"Understood. Regarding your question — {user.strip()[:160]} — "
            "here is my best answer based on the available context."
        )

    def _retry_last_apple_answer(self) -> str:
        if self.ctx is None:
            return "Could you repeat your question?"
        q = self.ctx.last_apple_question()
        if not q and self.ctx.apple_topic == "unset":
            return "Could you clarify what you'd like me to answer?"
        if self.ctx.apple_topic == "company":
            return apple_price_reply(fruit=False)
        if self.ctx.apple_topic == "fruit" or _has_fruit_preference(self.ctx):
            return apple_price_reply(fruit=True)
        return apple_price_reply(fruit=False)
