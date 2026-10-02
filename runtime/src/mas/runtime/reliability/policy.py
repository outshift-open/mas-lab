#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Spec-driven infra retry settings (engine I/O). Circuit breaker is a plugin."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from mas.runtime.reliability.classes import FailureClass


def _binding_error(message: str) -> Exception:
    from mas.runtime.spec.gov import SpecBindingError

    return SpecBindingError(message)

_FAILURE_CLASSES = {item.value: item for item in FailureClass}


def _parse_classes(raw: Any, *, field_name: str, default: tuple[FailureClass, ...]) -> tuple[FailureClass, ...]:
    if raw is None:
        return default
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise _binding_error(f"{field_name} must be a list of failure-class names")
    out: list[FailureClass] = []
    for item in raw:
        key = str(item).strip().lower()
        if key not in _FAILURE_CLASSES:
            raise _binding_error(
                f"{field_name}: unknown failure class {item!r} "
                f"(expected {sorted(_FAILURE_CLASSES)})"
            )
        out.append(_FAILURE_CLASSES[key])
    return tuple(out) or default


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to re-issue the same HTTP/tool call (infra layer)."""

    max_attempts: int = 4
    backoff_s: float = 0.5
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retry_on: tuple[FailureClass, ...] = (
        FailureClass.TRANSIENT,
        FailureClass.UNAVAILABLE,
    )
    require_idempotent: bool = False
    max_backoff_s: float | None = None

    def delay_for(self, attempt: int) -> float:
        """Sleep before attempt ``attempt`` (0-based, after the first failure)."""
        delay = max(0.0, self.backoff_s) * (self.backoff_multiplier ** max(0, attempt))
        if self.max_backoff_s is not None:
            delay = min(delay, max(0.0, self.max_backoff_s))
        if self.jitter and delay > 0:
            delay += random.uniform(0.0, delay * 0.25)
        return delay

    def allows(self, failure_class: FailureClass, *, idempotent: bool) -> bool:
        if failure_class not in self.retry_on:
            return False
        if self.require_idempotent and failure_class == FailureClass.TRANSIENT and not idempotent:
            return False
        return True

    def to_mapping(self) -> dict[str, Any]:
        out = {
            "max_attempts": self.max_attempts,
            "backoff_s": self.backoff_s,
            "backoff_multiplier": self.backoff_multiplier,
            "jitter": self.jitter,
            "retry_on": [item.value for item in self.retry_on],
            "require_idempotent": self.require_idempotent,
        }
        if self.max_backoff_s is not None:
            out["max_backoff_s"] = self.max_backoff_s
        return out

    @classmethod
    def llm_default(cls) -> RetryPolicy:
        """Chat completions: retry dropped sockets, 429/5xx, and connect-refused."""
        return cls(
            retry_on=(FailureClass.TRANSIENT, FailureClass.UNAVAILABLE),
        )

    @classmethod
    def tools_default(cls) -> RetryPolicy:
        return cls(
            max_attempts=2,
            retry_on=(FailureClass.TRANSIENT, FailureClass.UNAVAILABLE),
            require_idempotent=True,
        )

    @classmethod
    def from_mapping(cls, raw: Any, *, field_name: str, default: RetryPolicy | None = None) -> RetryPolicy:
        base = default or cls()
        if raw is None:
            return base
        if not isinstance(raw, Mapping):
            raise _binding_error(f"{field_name} must be an object")
        allowed = {
            "max_attempts",
            "backoff_s",
            "backoff_multiplier",
            "jitter",
            "retry_on",
            "require_idempotent",
            "max_backoff_s",
        }
        unknown = set(raw) - allowed
        if unknown:
            raise _binding_error(f"{field_name}: unknown field {sorted(unknown)[0]!r}")
        max_attempts = raw.get("max_attempts", base.max_attempts)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise _binding_error(f"{field_name}.max_attempts must be an integer >= 1")
        backoff_s = raw.get("backoff_s", base.backoff_s)
        if not isinstance(backoff_s, (int, float)) or isinstance(backoff_s, bool) or backoff_s < 0:
            raise _binding_error(f"{field_name}.backoff_s must be a number >= 0")
        multiplier = raw.get("backoff_multiplier", base.backoff_multiplier)
        if not isinstance(multiplier, (int, float)) or isinstance(multiplier, bool) or multiplier < 1:
            raise _binding_error(f"{field_name}.backoff_multiplier must be a number >= 1")
        jitter = base.jitter if raw.get("jitter") is None else bool(raw.get("jitter"))
        require_idempotent = (
            base.require_idempotent
            if raw.get("require_idempotent") is None
            else bool(raw.get("require_idempotent"))
        )
        max_backoff = base.max_backoff_s if raw.get("max_backoff_s") is None else raw.get("max_backoff_s")
        if max_backoff is not None and (
            not isinstance(max_backoff, (int, float)) or isinstance(max_backoff, bool) or max_backoff < 0
        ):
            raise _binding_error(f"{field_name}.max_backoff_s must be a number >= 0 or null")
        return cls(
            max_attempts=max_attempts,
            backoff_s=float(backoff_s),
            backoff_multiplier=float(multiplier),
            jitter=jitter,
            retry_on=_parse_classes(
                raw.get("retry_on"), field_name=f"{field_name}.retry_on", default=base.retry_on
            ),
            require_idempotent=require_idempotent,
            max_backoff_s=None if max_backoff is None else float(max_backoff),
        )


def llm_retry_policy(**overrides: Any) -> RetryPolicy:
    """RetryPolicy for live LLM HTTP, including ``MAS_LLM_HTTP_*`` env overrides."""
    policy = RetryPolicy.llm_default()
    if overrides:
        policy = RetryPolicy.from_mapping(overrides, field_name="llm.retry", default=policy)
    return apply_llm_retry_env(policy)


def apply_llm_retry_env(policy: RetryPolicy) -> RetryPolicy:
    """``MAS_LLM_HTTP_RETRIES`` is extra retries (attempts = retries + 1)."""
    updates: dict[str, Any] = {}
    if "MAS_LLM_HTTP_RETRIES" in os.environ:
        raw = os.environ.get("MAS_LLM_HTTP_RETRIES") or "3"
        updates["max_attempts"] = max(1, int(raw) + 1)
    if "MAS_LLM_HTTP_RETRY_BACKOFF" in os.environ:
        raw = os.environ.get("MAS_LLM_HTTP_RETRY_BACKOFF") or "0.5"
        updates["backoff_s"] = max(0.05, float(raw))
        updates["jitter"] = False
    return replace(policy, **updates) if updates else policy


_CIRCUIT_KEYS = frozenset({"failure_threshold", "reset_timeout_s", "on", "enabled", "plugin"})


def _library_plugin_from_mapping(
    raw: Any,
    *,
    plugin_type: str,
    field_name: str,
    allowed: frozenset[str],
) -> Any:
    """Instantiate a registered library plugin, or None when the spec omits it.

    No plugin class is named here — same registry lookup as governance.
    """
    import inspect

    from mas.runtime.registry import get_registry

    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise _binding_error(f"{field_name} must be an object or null")
    data = dict(raw)
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    unknown = set(data) - allowed
    if unknown:
        raise _binding_error(f"{field_name}: unknown field {sorted(str(k) for k in unknown)[0]!r}")
    if data.get("enabled") is False:
        return None
    plugin_name = str(data.pop("plugin", "") or "").strip()
    registry = get_registry()
    if not plugin_name:
        plugin_name = registry.default_for(plugin_type) or plugin_type
    variant = registry.resolve_by_type(plugin_type, plugin_name)
    if variant is None:
        raise _binding_error(f"{field_name}: {plugin_type} plugin {plugin_name!r} was not found")
    plugin_cls = variant.load_class()
    try:
        params = inspect.signature(plugin_cls).parameters
    except (TypeError, ValueError):
        kwargs = dict(data)
    else:
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            kwargs = dict(data)
        else:
            kwargs = {key: value for key, value in data.items() if key in params}
    return plugin_cls(**kwargs)


@dataclass(frozen=True)
class ReliabilitySettings:
    """Engine knobs parsed from ``spec.control``.

    Circuit breaker is a library plugin (duck-typed). Ingress ``error_policy``
    lives on ``retry_on_error``. Neither is kernel state.
    """

    llm_retry: RetryPolicy = field(default_factory=RetryPolicy.llm_default)
    tool_retry: RetryPolicy = field(default_factory=RetryPolicy.tools_default)
    circuit_breaker: Any = field(default=None)

    @classmethod
    def from_spec(
        cls,
        spec: Mapping[str, Any] | None,
        *,
        llm_proxy: Mapping[str, Any] | None = None,
    ) -> ReliabilitySettings:
        control = (spec or {}).get("control") if isinstance(spec, Mapping) else None
        control = control if isinstance(control, Mapping) else {}
        retry_raw = control.get("retry")
        if retry_raw is None:
            retry_raw = {}
        elif not isinstance(retry_raw, Mapping):
            raise _binding_error("spec.control.retry must be an object")
        else:
            unknown_retry = set(retry_raw) - {"llm", "tools"}
            if unknown_retry:
                raise _binding_error(f"spec.control.retry: unknown field {sorted(unknown_retry)[0]!r}")
        proxy = llm_proxy if isinstance(llm_proxy, Mapping) else {}
        llm = RetryPolicy.from_mapping(
            retry_raw.get("llm") if retry_raw.get("llm") is not None else proxy.get("retry"),
            field_name="spec.control.retry.llm",
            default=RetryPolicy.llm_default(),
        )
        llm = apply_llm_retry_env(llm)
        tools = RetryPolicy.from_mapping(
            retry_raw.get("tools"),
            field_name="spec.control.retry.tools",
            default=RetryPolicy.tools_default(),
        )
        return cls(
            llm_retry=llm,
            tool_retry=tools,
            circuit_breaker=_library_plugin_from_mapping(
                control.get("circuit_breaker"),
                plugin_type="circuit_breaker",
                field_name="spec.control.circuit_breaker",
                allowed=_CIRCUIT_KEYS,
            ),
        )
