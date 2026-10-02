#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Infra access pipeline — middleware wraps EngineContract before real provider.

Implementations register as ``type: infra_middleware``. This module owns the
protocol, registry dispatch, and the bidirectional reply facade — no plugin
class names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


class InfraMiddleware(Protocol):
    middleware_id: str

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn: ...

    async def ainvoke(self, io: InvokeEngineIo) -> EngineIoReturn: ...

    def exchange_preview(self, op: str, *, correlation_id: int = 0) -> str: ...


def apply_middleware(engine: Any, spec: dict[str, Any]) -> Any:
    """Wrap engine with one registered infra middleware, or leave it unchanged."""
    mid = str(spec.get("middleware") or spec.get("id") or "").strip().lower()
    if not mid:
        return engine
    params = dict(spec.get("params") or {})
    from mas.runtime.registry import get_registry

    variant = get_registry().resolve_by_type("infra_middleware", mid)
    if variant is None:
        return engine
    plugin_cls = variant.load_class()
    wrap = getattr(plugin_cls, "wrap", None)
    if callable(wrap):
        return wrap(engine, params)
    return plugin_cls(inner=engine, **params)


def wrap_pipeline(engine: Any, pipeline: list[dict[str, Any]]) -> Any:
    """Wrap engine with resolved infra middleware (forward + backward reply chain)."""
    return wrap_bidirectional_pipeline(engine, pipeline)


def wrap_bidirectional_pipeline(engine: Any, pipeline: list[dict[str, Any]]) -> Any:
    """Apply infra middleware forward chain, then backward reply transforms on LLM_CALL."""
    if not pipeline:
        return engine
    wrapped = engine
    for spec in reversed(pipeline):
        wrapped = apply_middleware(wrapped, spec)
    return BidirectionalPipelineEngine(inner=wrapped, pipeline_steps=list(pipeline))


@dataclass
class BidirectionalPipelineEngine:
    """Engine facade aligned with ctl ``BidirectionalInfraPipeline`` reply pass."""

    inner: Any
    pipeline_steps: list[dict[str, Any]]

    def exchange_preview(self, op: str, *, correlation_id: int = 0) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        if callable(preview):
            return str(preview(op, correlation_id=correlation_id) or "")
        return ""

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        ret = self.inner.invoke(io)
        if io.op != "LLM_CALL" or ret.response_kind != "MODEL_TEXT" or not ret.text:
            return ret
        from mas.runtime.engine.infra_chain import BidirectionalInfraPipeline, InfraChainContext

        chain = BidirectionalInfraPipeline.from_pipeline_steps(self.pipeline_steps)
        ctx = InfraChainContext(
            query={"content": ret.text, "correlation_id": io.correlation_id},
            correlation_id=io.correlation_id,
            target="LLM_CALL",
        )
        out = chain.backward_reply(ctx, {"content": ret.text})
        new_text = str(out.get("content") or ret.text)
        if new_text == ret.text:
            return ret
        return ret.model_copy(update={"text": new_text})

    async def ainvoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        ret = await self.inner.ainvoke(io)
        if io.op != "LLM_CALL" or ret.response_kind != "MODEL_TEXT" or not ret.text:
            return ret
        from mas.runtime.engine.infra_chain import BidirectionalInfraPipeline, InfraChainContext

        chain = BidirectionalInfraPipeline.from_pipeline_steps(self.pipeline_steps)
        ctx = InfraChainContext(
            query={"content": ret.text, "correlation_id": io.correlation_id},
            correlation_id=io.correlation_id,
            target="LLM_CALL",
        )
        out = chain.backward_reply(ctx, {"content": ret.text})
        new_text = str(out.get("content") or ret.text)
        if new_text == ret.text:
            return ret
        return ret.model_copy(update={"text": new_text})

    def reset_turn_state(self) -> None:
        reset_fn = getattr(self.inner, "reset_turn_state", None)
        if callable(reset_fn):
            reset_fn()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def summarize_messages(self, messages: list[dict[str, Any]], *, model: str | None = None) -> str:
        from mas.runtime.engine.protocol import CompactionSummarizeEngine

        inner = self.inner
        if not isinstance(inner, CompactionSummarizeEngine):
            raise TypeError(f"{type(inner).__name__} does not implement CompactionSummarizeEngine")
        if model is not None:
            return inner.summarize_messages(messages, model=model)
        return inner.summarize_messages(messages)
