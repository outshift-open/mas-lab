#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Infra access pipeline — middleware wraps EngineContract before real provider."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mas.runtime.engine.llm_cache import (
    load_cache,
    middleware_cache_deserialize,
    middleware_cache_serialize,
    persist_cache,
)
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


class InfraMiddleware(Protocol):
    middleware_id: str

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn: ...

    def exchange_preview(self, op: str) -> str: ...


@dataclass
class LlmCacheMiddleware:
    """Cache LLM_CALL results on disk — sits in front of live infra.

    allow_read / allow_write are independent (both default True, like a
    normal read-through cache); a demo can compose write-only (build the
    cache), read-only (replay it), or both (default) purely via infra
    manifest params — no code branching per mode.
    """

    inner: Any
    middleware_id: str = "llm_cache"
    cache_path: Path | None = None
    allow_read: bool = True
    allow_write: bool = True
    # Replay-only mode: never falls through to `inner` on a cache miss, so a
    # stacked infra manifest can guarantee zero calls reach the real provider
    # (e.g. a fast demo replay with no live LLM/network configured at all).
    raise_on_miss: bool = False
    include_preview: bool = False
    _cache: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.cache_path:
            self._cache = load_cache(self.cache_path)

    def exchange_preview(self, op: str) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        if callable(preview):
            head = str(preview(op) or "")
            return f"[llm_cache middleware]\n{head}".strip()
        return "[llm_cache middleware]"

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if not (self.allow_read or self.allow_write) or io.op != "LLM_CALL":
            return self.inner.invoke(io)
        # Exactly one exchange_preview() call per invoke(): LiveLlmEngine's
        # preview resets ctx._assembly_correlation_id as a side effect, so
        # calling it more than once here (as the old separate tool-results
        # check + cache-key computation did) corrupted textual tool-call
        # parsing correlation state on every cached turn.
        # No tool-results skip: the cache key is the full preview text
        # (conversation so far, including any prior tool result), so a
        # different tool outcome naturally produces a different key and a
        # fresh miss -- there is nothing to protect against by excluding
        # these turns, and skipping them defeats caching a whole agentic
        # turn, where the useful answer is almost always the post-tool-call
        # completion.
        preview = self._preview(io)
        key = hashlib.sha256(preview.encode()).hexdigest()
        if self.allow_read and key in self._cache:
            return middleware_cache_deserialize(self._cache[key], io.correlation_id)
        if self.allow_read and self.raise_on_miss:
            raise RuntimeError(f"llm_cache miss (raise_on_miss=true) for key {key}")
        ret = self.inner.invoke(io)
        if (
            self.allow_write
            and ret.response_kind == "MODEL_TEXT"
            and ret.next_step in {"STOP", "TOOL_CALL", "PARALLEL_TOOL_CALLS"}
        ):
            self._cache[key] = middleware_cache_serialize(
                ret,
                include_preview=self.include_preview,
                preview=preview,
            )
            self._persist()
        return ret

    def reset_turn_state(self) -> None:
        reset_fn = getattr(self.inner, "reset_turn_state", None)
        if callable(reset_fn):
            reset_fn()

    def _preview(self, io: InvokeEngineIo) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        return str(preview("LLM_CALL") if callable(preview) else io.correlation_id)

    def _persist(self) -> None:
        if not self.cache_path:
            return
        persist_cache(self.cache_path, self._cache)


@dataclass
class FaultInjectMiddleware:
    """Inject random LLM failures — chaos-lite in front of any provider."""

    inner: Any
    middleware_id: str = "fault_inject"
    rate: float = 0.0
    status_codes: list[int] = field(default_factory=lambda: [503])
    message: str = "injected fault"

    def exchange_preview(self, op: str) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        if callable(preview):
            head = str(preview(op) or "")
            return f"[fault_inject middleware rate={self.rate}]\n{head}".strip()
        return f"[fault_inject middleware rate={self.rate}]"

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if io.op == "LLM_CALL" and self.rate > 0 and random.random() < self.rate:
            code = self.status_codes[0] if self.status_codes else 503
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="ERROR",
                next_step="STOP",
                text=f"{code}: {self.message}",
            )
        return self.inner.invoke(io)


def apply_middleware(engine: Any, spec: dict[str, Any]) -> Any:
    """Wrap engine with one infra middleware entry from resolved pipeline."""
    mid = str(spec.get("middleware") or spec.get("id") or "")
    params = dict(spec.get("params") or {})
    if mid in {"llm_cache", "llm-cache"}:
        path_raw = params.get("cache_path") or params.get("path")
        path = Path(str(path_raw)) if path_raw else None
        allow_read = params.get("allow_read", params.get("enabled", True)) is not False
        allow_write = params.get("allow_write", params.get("enabled", True)) is not False
        raise_on_miss = params.get("raise_on_miss", False) is True
        include_preview = params.get("include_preview", False) is True
        return LlmCacheMiddleware(
            inner=engine,
            cache_path=path,
            allow_read=bool(allow_read),
            allow_write=bool(allow_write),
            raise_on_miss=raise_on_miss,
            include_preview=bool(include_preview),
        )
    if mid in {"fault_inject", "fault-inject", "chaos_lite", "chaos-lite"}:
        rate = float(params.get("rate") or params.get("failure_rate") or 0.0)
        codes_raw = params.get("status_codes") or params.get("errors") or [503]
        codes = [int(c) for c in codes_raw] if isinstance(codes_raw, list) else [503]
        msg = str(params.get("message") or "injected fault")
        return FaultInjectMiddleware(inner=engine, rate=max(0.0, min(1.0, rate)), status_codes=codes, message=msg)
    return engine


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

    def exchange_preview(self, op: str) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        if callable(preview):
            return str(preview(op) or "")
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

    def reset_turn_state(self) -> None:
        reset_fn = getattr(self.inner, "reset_turn_state", None)
        if callable(reset_fn):
            reset_fn()

    def summarize_messages(self, messages: list[dict[str, Any]]) -> str:
        from mas.runtime.engine.protocol import CompactionSummarizeEngine

        inner = self.inner
        if not isinstance(inner, CompactionSummarizeEngine):
            raise TypeError(f"{type(inner).__name__} does not implement CompactionSummarizeEngine")
        return inner.summarize_messages(messages)
