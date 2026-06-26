#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Live LLM engine — OpenAI-compatible chat completions via httpx."""

from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mas.runtime.engine.llm_http import classify_llm_http_error, resolve_ssl_verify
from mas.runtime.engine.tools import openai_tools
from mas.runtime.engine.exchange_preview import format_llm_messages, format_tool_invoke
from mas.runtime.boundary.context.assemble import (
    assemble_llm_messages,
    has_tool_results,
    llm_request_tools,
    llm_tool_choice,
)
from mas.runtime.boundary.gov.budget import BudgetTracker, budget_from_manifest
from mas.runtime.engine.tutorial_tools import execute_tutorial_tool
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn

if TYPE_CHECKING:
    from mas.runtime.driver.mocks import AutoCtxAssembler

logger = logging.getLogger(__name__)


@dataclass
class LiveLlmEngine:
    """EngineContract implementation — calls remote LLM proxy / OpenAI API."""

    ctx: AutoCtxAssembler | None = None
    manifest: dict | None = None
    api_base: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    cache_path: Path | None = None
    use_cache: bool = True
    use_tool_loop: bool = False
    parallel_tool_calls: bool = True
    llm_proxy: dict[str, Any] | None = None
    _cache: dict[str, str] = field(default_factory=dict, init=False)
    _pending_tool: str = field(default="", init=False)
    _pending_tool_args: dict[str, Any] = field(default_factory=dict, init=False)
    _pending_tools_by_cid: dict[int, tuple[str, dict[str, Any]]] = field(
        default_factory=dict, init=False
    )
    _budget: BudgetTracker = field(default_factory=BudgetTracker, init=False)

    def set_scheduled_tool(self, name: str, arguments: dict[str, Any] | None = None) -> None:
        """Kernel-scheduled tool (e.g. plan-execute) — TLA: ToolMachine.tla."""
        self._pending_tool = name
        self._pending_tool_args = dict(arguments or {})

    def set_tool_for_correlation(
        self, correlation_id: int, name: str, arguments: dict[str, Any] | None = None
    ) -> None:
        self._pending_tools_by_cid[correlation_id] = (name, dict(arguments or {}))

    def __post_init__(self) -> None:
        self._budget = budget_from_manifest(self.manifest)
        if self.cache_path and self.cache_path.is_file():
            with contextlib.suppress(Exception):
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def reset_turn_state(self) -> None:
        self._pending_tool = ""
        self._pending_tool_args = {}
        self._pending_tools_by_cid.clear()

    def exchange_preview(self, op: str) -> str:
        """Ctl --trace: describe outbound LLM payload or pending tool call."""
        if op == "LLM_CALL":
            if self.ctx is not None:
                self.ctx._assembly_correlation_id = 0
            messages = self._build_messages()
            tool_defs = openai_tools(self.manifest) if self.use_tool_loop else []
            api_tools = llm_request_tools(messages, tools=tool_defs or None)
            tools_note = ""
            if tool_defs and api_tools is None and has_tool_results(messages):
                tools_note = "(omitted — answer-from-tool-result turn)"
            return format_llm_messages(messages, tools=api_tools, tools_note=tools_note)
        if op == "TOOL_CALL":
            tool = self._pending_tool or "tool"
            return format_tool_invoke(tool, self._pending_tool_args)
        return ""

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if io.op == "LLM_CALL":
            return self._llm_call(io)
        if io.op == "TOOL_CALL":
            if not self._budget.allow_tool():
                return EngineIoReturn(
                    correlation_id=io.correlation_id,
                    response_kind="ERROR",
                    next_step="STOP",
                    text="Budget exceeded: max tool calls reached.",
                )
            self._budget.note_tool()
            user = (self.ctx.last_user_text if self.ctx else "") or ""
            by_cid = self._pending_tools_by_cid.pop(io.correlation_id, None)
            if by_cid is not None:
                tool, args = by_cid
            else:
                tool = self._pending_tool or "tool"
                args = dict(self._pending_tool_args)
                self._pending_tool = ""
                self._pending_tool_args = {}
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TOOL_RESULT",
                next_step="LLM_CALL" if self.use_tool_loop else "STOP",
                text=execute_tutorial_tool(tool, ctx=self.ctx, user=user, arguments=args),
            )
        if io.op == "MEMORY_OP":
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text="Memory updated.",
            )
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="ERROR",
            next_step="STOP",
            text=f"Unsupported operation: {io.op}",
        )

    def _llm_call(self, io: InvokeEngineIo) -> EngineIoReturn:
        if not self._budget.allow_llm():
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text="Budget exceeded: max LLM calls reached.",
            )
        self._budget.note_llm()
        if self.ctx is not None:
            self.ctx._assembly_correlation_id = io.correlation_id
        messages = self._build_messages()
        tool_defs = openai_tools(self.manifest) if self.use_tool_loop else []
        tools = llm_request_tools(messages, tools=tool_defs or None)
        answering_from_tools = has_tool_results(messages)

        cache_key = self._cache_key(messages, tool_defs)
        if self.use_cache and not answering_from_tools and cache_key in self._cache:
            text = self._cache[cache_key]
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text=text,
            )

        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text=f"Missing API key env {self.api_key_env} for live LLM.",
            )

        try:
            message = self._chat_completion(
                messages,
                api_key=api_key,
                tools=tools,
                temperature=0.0 if answering_from_tools else self.temperature,
            )
        except Exception as exc:
            logger.debug("live LLM call failed", exc_info=True)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text=classify_llm_http_error(exc),
            )

        tool_calls = message.get("tool_calls") or []
        if tool_calls and self.use_tool_loop:
            parsed: list[tuple[str, dict[str, Any]]] = []
            for call in tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "tool")
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args = {"raw": raw_args}
                parsed.append((name, args))
            if len(parsed) > 1 and self.parallel_tool_calls:
                from mas.runtime.schema.ingress import ToolCallSpec

                return EngineIoReturn(
                    correlation_id=io.correlation_id,
                    response_kind="MODEL_TEXT",
                    next_step="PARALLEL_TOOL_CALLS",
                    parallel_tools=tuple(
                        ToolCallSpec(tool_name=name, tool_arguments=args) for name, args in parsed
                    ),
                    text="",
                )
            name, args = parsed[0]
            self._pending_tool = name
            self._pending_tool_args = args
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="TOOL_CALL",
                tool_name=name,
                tool_arguments=args,
                text="",
            )

        text = str(message.get("content") or "").strip()
        if self.use_cache and not answering_from_tools:
            self._cache[cache_key] = text
            self._persist_cache()

        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="MODEL_TEXT",
            next_step="STOP",
            text=text,
        )

    def _build_messages(self) -> list[dict[str, Any]]:
        if self.ctx:
            return assemble_llm_messages(self.ctx, manifest=self.manifest)
        return [{"role": "user", "content": "Hello"}]

    def _chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        api_key: str,
        tools: list[dict[str, Any]] | None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        import httpx

        url = self.api_base.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            choice = llm_tool_choice(messages, tools=tools)
            if choice:
                payload["tool_choice"] = choice
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        verify = resolve_ssl_verify(self.llm_proxy)
        with httpx.Client(timeout=120.0, verify=verify) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return {}
        return choices[0].get("message") or {}

    def _cache_key(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
        import hashlib

        blob = json.dumps({"model": self.model, "messages": messages, "tools": tools}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _persist_cache(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
