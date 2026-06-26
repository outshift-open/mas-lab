#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Infra access pipeline — middleware wraps EngineContract before real provider."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


class InfraMiddleware(Protocol):
    middleware_id: str

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn: ...

    def exchange_preview(self, op: str) -> str: ...


@dataclass
class LlmCacheMiddleware:
    """Cache LLM_CALL results on disk — sits in front of live infra."""

    inner: Any
    middleware_id: str = "llm_cache"
    cache_path: Path | None = None
    enabled: bool = True
    _cache: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.cache_path and self.cache_path.is_file():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def exchange_preview(self, op: str) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        if callable(preview):
            head = str(preview(op) or "")
            return f"[llm_cache middleware]\n{head}".strip()
        return "[llm_cache middleware]"

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        if not self.enabled or io.op != "LLM_CALL":
            return self.inner.invoke(io)
        if self._request_has_tool_results():
            return self.inner.invoke(io)
        key = self._cache_key(io)
        if key in self._cache:
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text=self._cache[key],
            )
        ret = self.inner.invoke(io)
        if ret.response_kind == "MODEL_TEXT" and ret.text and ret.next_step == "STOP":
            if not self._request_has_tool_results():
                self._cache[key] = ret.text
                self._persist()
        return ret

    def reset_turn_state(self) -> None:
        reset_fn = getattr(self.inner, "reset_turn_state", None)
        if callable(reset_fn):
            reset_fn()

    def _request_has_tool_results(self) -> bool:
        preview = getattr(self.inner, "exchange_preview", None)
        if callable(preview):
            body = str(preview("LLM_CALL") or "")
            return "[tool call_id=" in body
        return False

    def _cache_key(self, io: InvokeEngineIo) -> str:
        preview = getattr(self.inner, "exchange_preview", None)
        body = str(preview("LLM_CALL") if callable(preview) else io.correlation_id)
        return hashlib.sha256(body.encode()).hexdigest()

    def _persist(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")


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
        enabled = params.get("enabled", True) is not False
        return LlmCacheMiddleware(inner=engine, cache_path=path, enabled=bool(enabled))
    if mid in {"fault_inject", "fault-inject", "chaos_lite", "chaos-lite"}:
        rate = float(params.get("rate") or params.get("failure_rate") or 0.0)
        codes_raw = params.get("status_codes") or params.get("errors") or [503]
        codes = [int(c) for c in codes_raw] if isinstance(codes_raw, list) else [503]
        msg = str(params.get("message") or "injected fault")
        return FaultInjectMiddleware(
            inner=engine, rate=max(0.0, min(1.0, rate)), status_codes=codes, message=msg
        )
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
