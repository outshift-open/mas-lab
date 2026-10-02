#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Live LLM engine — EngineContract over an LLMProvider plugin."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mas.runtime.boundary.context.assemble import (
    assemble_llm_messages,
    has_tool_results,
    llm_request_tools,
)
from mas.runtime.boundary.gov.budget import BudgetTracker, budget_from_manifest
from mas.runtime.engine.exchange_preview import ExchangeSnapshot, format_exchange_snapshot
from mas.runtime.engine.llm_http import classify_llm_http_error
from mas.runtime.engine.textual_tool_calls import maybe_recover_textual_tool_calls, repair_merged_arg_keys
from mas.runtime.engine.tool_dispatch import ToolExecutionError, execute_engine_tool
from mas.runtime.engine.tools import openai_tools
from mas.runtime.engine.llm_reasoning import (
    ReasoningSettings,
    coerce_reasoning_settings,
    reasoning_settings_from_manifest,
)
from mas.runtime.engine.llm_request import extra_from_manifest, sampling_settings_from_manifest
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn

if TYPE_CHECKING:
    from mas.runtime.driver.mocks import AutoCtxAssembler

logger = logging.getLogger(__name__)


@dataclass
class LiveLlmEngine:
    """EngineContract implementation — delegates chat completions to LLMProvider plugins."""

    ctx: AutoCtxAssembler | None = None
    manifest: dict | None = None
    api_base: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    # Reasoning models (Gemini 2.5, o-series) bill internal thinking against
    # max_tokens, so an unbounded budget can leave zero tokens for the answer.
    reasoning_effort: str | None = None
    reasoning: ReasoningSettings | dict[str, Any] | None = None
    extra_body: dict[str, Any] | None = None
    cache_path: Path | None = None
    use_cache: bool = True
    cache_read: bool = True
    cache_write: bool = True
    stream: bool = False
    use_tool_loop: bool = False
    parallel_tool_calls: bool = True
    llm_proxy: dict[str, Any] | None = None
    http_timeout: float | None = None
    manifest_dir: Path | None = None
    delegation: Any | None = None
    engine_tool_contracts: tuple[Any, ...] = ()
    delegation_peer_descriptions: dict[str, str] | None = None
    tool_provider: Any | None = None
    llm_provider: Any | None = None
    _pending_tool: str = field(default="", init=False)
    _pending_tool_args: dict[str, Any] = field(default_factory=dict, init=False)
    _pending_tools_by_cid: dict[int, tuple[str, dict[str, Any]]] = field(default_factory=dict, init=False)
    _offered_tool_names: list[str] = field(default_factory=list, init=False)
    _budget: BudgetTracker = field(default_factory=BudgetTracker, init=False)
    _model_access: Any | None = field(default=None, init=False)

    def set_scheduled_tool(self, name: str, arguments: dict[str, Any] | None = None) -> None:
        """Kernel-scheduled tool (e.g. plan-execute) — TLA: ToolMachine.tla."""
        self._pending_tool = name
        self._pending_tool_args = dict(arguments or {})

    def set_tool_for_correlation(self, correlation_id: int, name: str, arguments: dict[str, Any] | None = None) -> None:
        self._pending_tools_by_cid[correlation_id] = (name, dict(arguments or {}))

    def __post_init__(self) -> None:
        self.reasoning = coerce_reasoning_settings(
            self.reasoning if self.reasoning is not None else reasoning_settings_from_manifest(
                self.manifest, model=self.model
            ),
            effort=self.reasoning_effort,
        )
        self.reasoning_effort = self.reasoning.effort
        self.sampling = sampling_settings_from_manifest(self.manifest, model=self.model)
        if self.extra_body is None:
            self.extra_body = extra_from_manifest(self.manifest, model=self.model)
        self._budget = budget_from_manifest(self.manifest)
        if self.llm_provider is None:
            self.llm_provider = self._default_llm_provider()
        self.llm_provider = self._wrap_cache(self.llm_provider)
        # Tests that still inspect _model_access see the routed provider.
        self._model_access = self.llm_provider

    def _default_llm_provider(self) -> Any:
        from mas.runtime.registry.llm_provider_registry import llm_provider_from_infra

        proxy = dict(self.llm_proxy or {})
        proxy.setdefault("api_base", self.api_base)
        proxy.setdefault("api_key_env", self.api_key_env)
        if self.http_timeout is not None:
            proxy.setdefault("timeout", self.http_timeout)
        return llm_provider_from_infra(
            proxy,
            manifest=self.manifest,
            stream=self.stream,
            reasoning_effort=self.reasoning.effort,
            reasoning=self.reasoning.to_spec_dict(),
        )

    def _wrap_cache(self, provider: Any) -> Any:
        if not (self.use_cache and (self.cache_read or self.cache_write) and self.cache_path):
            return provider
        from mas.runtime.registry.llm_provider_registry import wrap_llm_provider_cache

        return wrap_llm_provider_cache(
            provider,
            cache_path=self.cache_path,
            cache_read=self.cache_read,
            cache_write=self.cache_write,
        )

    def reset_turn_state(self) -> None:
        self._pending_tool = ""
        self._pending_tool_args = {}
        self._pending_tools_by_cid.clear()
        self._offered_tool_names = []

    def summarize_messages(self, messages: list[dict[str, Any]], *, model: str | None = None) -> str:
        """One-off chat completion. The summarizer plugin builds the prompt."""
        if not self._budget.allow_llm():
            raise RuntimeError(
                "history summarizer: LLM call budget "
                "exceeded (spec.budget.max_llm_calls)"
            )
        self._budget.note_llm()
        use_model = (model or self.model or "").strip() or self.model
        logger.info(
            "history summarizer: completing %d message(s) model=%s%s",
            len(messages),
            use_model,
            " (override)" if model and model != self.model else "",
        )
        api_key = os.environ.get(self.api_key_env, "")
        message = self._chat_completion(
            messages, api_key=api_key, tools=None, temperature=0.0, model=use_model
        )
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
        return str(content or "").strip()

    def exchange_snapshot(self, op: str, *, correlation_id: int = 0) -> ExchangeSnapshot:
        """Structured outbound LLM payload or pending tool call. Not a display string.

        ``correlation_id`` is this op's real id when the caller has one (a
        cache-key preview, an exchange-log entry) — assembling messages
        records context-assembly telemetry tagged with whatever id is set on
        ``ctx``, so a preview must pass the real id through rather than
        leaving the previous call's id in place (stale) or zeroing it
        (untraceable): both defeat mapping that telemetry back to its LLM
        call, which matters most on a cache hit, where this preview is the
        only assembly this op ever does.
        """
        if op == "LLM_CALL":
            if self.ctx is not None:
                self.ctx._assembly_correlation_id = correlation_id
            tool_defs = self._tool_defs()
            messages = self._build_messages(tools=tool_defs)
            api_tools = llm_request_tools(messages, tools=tool_defs or None)
            tools_note = ""
            if tool_defs and api_tools is None and has_tool_results(messages):
                tools_note = "(omitted — answer-from-tool-result turn)"
            return ExchangeSnapshot(messages=messages, tools=api_tools, tools_note=tools_note)
        if op == "TOOL_CALL":
            return ExchangeSnapshot(
                tool_name=self._pending_tool or "tool",
                arguments=dict(self._pending_tool_args),
            )
        return ExchangeSnapshot()

    def exchange_preview(self, op: str, *, correlation_id: int = 0) -> str:
        """Pretty-print of exchange_snapshot (cache keys, tests). Not interchange."""
        return format_exchange_snapshot(self.exchange_snapshot(op, correlation_id=correlation_id))

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
            try:
                text = execute_engine_tool(
                    tool,
                    delegation=self.delegation,
                    ctx=self.ctx,
                    user=user,
                    arguments=args,
                    tool_provider=self.tool_provider,
                    engine_contracts=self.engine_tool_contracts,
                    correlation_id=io.correlation_id,
                    # This TOOL_CALL's own resolved call_id (attached by the
                    # driver — see InvokeEngineIo.call_id) — forwarded as the
                    # caller identity for a delegate_to_* call, so the
                    # delegate's own execution_start.parent_call_id is real,
                    # not reconstructed from timestamps.
                    caller_call_id=io.call_id,
                )
            except ToolExecutionError as exc:
                # The model named a tool this agent cannot run. Return that as
                # the tool observation so the same agent can pick a tool it
                # was actually given, instead of aborting the turn.
                text = self._unavailable_tool_observation(tool, exc)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TOOL_RESULT",
                next_step="LLM_CALL" if self.use_tool_loop else "STOP",
                text=text,
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

    async def ainvoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if io.op == "LLM_CALL":
            return await self._allm_call(io)
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
            try:
                from mas.runtime.engine.tool_dispatch import aexecute_engine_tool

                text = await aexecute_engine_tool(
                    tool,
                    delegation=self.delegation,
                    ctx=self.ctx,
                    user=user,
                    arguments=args,
                    tool_provider=self.tool_provider,
                    engine_contracts=self.engine_tool_contracts,
                    correlation_id=io.correlation_id,
                    caller_call_id=io.call_id,
                )
            except ToolExecutionError as exc:
                text = self._unavailable_tool_observation(tool, exc)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TOOL_RESULT",
                next_step="LLM_CALL" if self.use_tool_loop else "STOP",
                text=text,
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
        tool_defs = self._tool_defs()
        messages = self._build_messages(tools=tool_defs)
        tools = llm_request_tools(messages, tools=tool_defs or None)
        answering_from_tools = has_tool_results(messages)
        try:
            message = self._chat_completion(
                messages,
                api_key=os.environ.get(self.api_key_env, ""),
                tools=tools,
                temperature=0.0 if answering_from_tools else self.temperature,
            )
        except Exception as exc:
            logger.debug("LLM provider call failed", exc_info=True)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text=classify_llm_http_error(exc),
                offered_tools=list(self._offered_tool_names),
            )

        usage = message.pop("usage", None) or {}
        finish_reason = message.pop("finish_reason", None) or ""
        return self._message_to_engine_return(
            io, message, messages, tool_defs, answering_from_tools, usage, finish_reason
        )

    async def _allm_call(self, io: InvokeEngineIo) -> EngineIoReturn:
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
        tool_defs = self._tool_defs()
        messages = self._build_messages(tools=tool_defs)
        tools = llm_request_tools(messages, tools=tool_defs or None)
        answering_from_tools = has_tool_results(messages)
        try:
            message = await self._achat_completion(
                messages,
                api_key=os.environ.get(self.api_key_env, ""),
                tools=tools,
                temperature=0.0 if answering_from_tools else self.temperature,
            )
        except asyncio.CancelledError:
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text="cancelled",
                finish_reason="cancelled",
                offered_tools=list(self._offered_tool_names),
            )
        except Exception as exc:
            logger.debug("LLM provider call failed", exc_info=True)
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text=classify_llm_http_error(exc),
                offered_tools=list(self._offered_tool_names),
            )

        usage = message.pop("usage", None) or {}
        finish_reason = message.pop("finish_reason", None) or ""
        return self._message_to_engine_return(
            io, message, messages, tool_defs, answering_from_tools, usage, finish_reason
        )

    def _message_to_engine_return(
        self,
        io: InvokeEngineIo,
        message: dict[str, Any],
        messages: list[dict[str, Any]],
        tool_defs: list[dict[str, Any]],
        answering_from_tools: bool,
        usage: dict[str, Any],
        finish_reason: str,
    ) -> EngineIoReturn:
        _ = messages, answering_from_tools
        message = maybe_recover_textual_tool_calls(message, tool_defs)
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
                if isinstance(args, dict):
                    args = repair_merged_arg_keys(args)
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
                    usage=usage,
                    finish_reason=finish_reason,
                    offered_tools=self._names_from_tool_defs(tool_defs),
                    model=self.model,
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
                usage=usage,
                finish_reason=finish_reason,
                offered_tools=self._names_from_tool_defs(tool_defs),
                model=self.model,
            )

        text = str(message.get("content") or "").strip()
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="MODEL_TEXT",
            next_step="STOP",
            text=text,
            usage=usage,
            finish_reason=finish_reason,
            offered_tools=self._names_from_tool_defs(tool_defs),
            model=self.model,
        )

    def _build_messages(self, *, tools: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        if self.ctx:
            return assemble_llm_messages(self.ctx, manifest=self.manifest, tools=tools)
        return [{"role": "user", "content": "Hello"}]

    def _tool_defs(self) -> list[dict[str, Any]]:
        """OpenAI tool schemas for this agent, and the names recorded on the call."""
        if not self.use_tool_loop:
            self._offered_tool_names = []
            return []
        tool_defs = openai_tools(
            self.manifest,
            base_dir=self.manifest_dir,
            tool_provider=self.tool_provider,
            peer_descriptions=self.delegation_peer_descriptions,
            ctx=self.ctx,
        )
        self._offered_tool_names = self._names_from_tool_defs(tool_defs)
        return tool_defs

    @staticmethod
    def _names_from_tool_defs(tool_defs: list[dict[str, Any]] | None) -> list[str]:
        names: list[str] = []
        for tool in tool_defs or []:
            fn = tool.get("function") if isinstance(tool, dict) else None
            name = str((fn or {}).get("name") or "") if isinstance(fn, dict) else ""
            if name:
                names.append(name)
        return names

    def _unavailable_tool_observation(self, tool: str, exc: BaseException) -> str:
        available = ", ".join(self._offered_tool_names) if self._offered_tool_names else "(none)"
        return f"{exc}. Available tools: {available}."

    def _chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        api_key: str,
        tools: list[dict[str, Any]] | None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch to ``llm_provider``. Tests may patch this method."""
        provider = self.llm_provider
        if provider is None:
            raise RuntimeError("no LLM provider configured")
        on_chunk = getattr(self.ctx, "on_stream_chunk", None) if self.ctx is not None else None
        use_model = (model or self.model or "").strip() or self.model
        kwargs: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "tools": tools,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "on_stream_chunk": on_chunk,
            "api_key": api_key,
            "reasoning_effort": self.reasoning.effort,
            "reasoning": self.reasoning,
            "sampling": self.sampling.to_spec_dict() or None,
            "extra_body": self.extra_body or None,
        }
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if not hasattr(provider, "chat_completion"):
            raise RuntimeError(f"LLM provider {type(provider).__name__} has no chat_completion")
        return provider.chat_completion(**kwargs)

    async def _achat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        api_key: str,
        tools: list[dict[str, Any]] | None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch to ``llm_provider.achat_completion``. Tests may patch this method."""
        provider = self.llm_provider
        if provider is None:
            raise RuntimeError("no LLM provider configured")
        on_chunk = getattr(self.ctx, "on_stream_chunk", None) if self.ctx is not None else None
        use_model = (model or self.model or "").strip() or self.model
        kwargs: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "tools": tools,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "on_stream_chunk": on_chunk,
            "api_key": api_key,
            "reasoning_effort": self.reasoning.effort,
            "reasoning": self.reasoning,
            "sampling": self.sampling.to_spec_dict() or None,
            "extra_body": self.extra_body or None,
        }
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if not hasattr(provider, "achat_completion"):
            raise RuntimeError(
                f"LLM provider {type(provider).__name__} has no achat_completion "
                "(async twin of chat_completion is required; worker-thread fallback is not supported)"
            )
        stream_iter = getattr(provider, "achat_completion_stream", None)
        if callable(stream_iter) and kwargs.get("stream"):
            return await self._achat_completion_streamed(stream_iter, kwargs)
        return await provider.achat_completion(**kwargs)

    async def _achat_completion_streamed(self, stream_iter: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Yielded chunks are obs ``llm_delta``, not Mealy ticks. Cancel between awaits."""
        assembled: dict[str, Any] | None = None
        parts: list[str] = []
        async for chunk in stream_iter(**kwargs):
            text = ""
            if isinstance(chunk, dict) and ("role" in chunk or "tool_calls" in chunk) and "delta" not in chunk:
                assembled = chunk
                text = str(chunk.get("content") or "")
            elif isinstance(chunk, dict):
                text = str(chunk.get("delta") or chunk.get("content") or "")
                parts.append(text)
            else:
                text = str(chunk)
                parts.append(text)
            if text:
                self._emit_llm_delta(text)
        if assembled is not None:
            return assembled
        return {"role": "assistant", "content": "".join(parts), "finish_reason": "stop"}

    def _emit_llm_delta(self, text: str) -> None:
        op = getattr(self.ctx, "observability", None) if self.ctx is not None else None
        record = getattr(op, "record_session", None) if op is not None else None
        if callable(record):
            record("llm_delta", text=text)
