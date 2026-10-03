#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Reasoning / thinking controls for LLMProvider chat completions.

``spec.models[].reasoning`` is the agent-facing surface. The OpenAI-compatible
plugin maps it onto Chat Completions fields; local sanitization keeps
chain-of-thought out of working memory even when a proxy still returns it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

REASONING_EFFORTS = (
    "none",
    "disable",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
_EFFORT_SET = frozenset(REASONING_EFFORTS)
_DISABLED_EFFORTS = frozenset({"none", "disable"})
_REASONING_MODES = frozenset({"standard", "pro"})
_REASONING_MESSAGE_KEYS = ("reasoning", "reasoning_content", "thinking", "reasoning_details")
_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think(?:ing)?>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think(?:ing)?>", re.IGNORECASE)


@dataclass(frozen=True)
class ReasoningSettings:
    """Canonical reasoning knobs resolved from ``spec.models[]``.

    * ``effort`` — how hard the model thinks (OpenAI ``reasoning_effort``).
    * ``budget_tokens`` — thinking-token cap (OpenRouter/Anthropic-style
      ``reasoning.max_tokens``; Gemini thinking budget via LiteLLM).
    * ``exclude`` — omit CoT from the assistant message (default true).
    * ``exclude_from_spec`` — user set ``exclude`` explicitly, so the plugin
      may send ``reasoning.exclude`` to proxies that support it. Official
      OpenAI Chat Completions may reject that extension, so it is not sent
      unless the spec asked for it.
    * ``mode`` — Responses / GPT-5.6 ``reasoning.mode`` (``standard`` / ``pro``).
    * ``think`` — Ollama / vLLM think flag (bool or ``low``/``medium``/``high``).
    * ``include`` — extra response parts (e.g. ``reasoning.encrypted_content``).
    """

    effort: str | None = None
    budget_tokens: int | None = None
    exclude: bool = True
    exclude_from_spec: bool = False
    mode: str | None = None
    think: bool | str | None = None
    include: tuple[str, ...] | None = None

    def thinking_enabled(self) -> bool:
        if self.think is False:
            return False
        if self.think is True or (isinstance(self.think, str) and self.think):
            return True
        return bool(self.effort) and self.effort not in _DISABLED_EFFORTS

    def to_spec_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.effort:
            out["effort"] = self.effort
        if self.budget_tokens is not None:
            out["budget_tokens"] = self.budget_tokens
        if self.exclude_from_spec:
            out["exclude"] = self.exclude
        elif not self.exclude:
            out["exclude"] = False
        if self.mode:
            out["mode"] = self.mode
        if self.think is not None:
            out["think"] = self.think
        if self.include:
            out["include"] = list(self.include)
        return out


def coerce_reasoning_settings(
    raw: ReasoningSettings | dict[str, Any] | None = None,
    *,
    effort: str | None = None,
) -> ReasoningSettings:
    if isinstance(raw, ReasoningSettings):
        if effort and not raw.effort:
            return ReasoningSettings(
                effort=_norm_effort(effort),
                budget_tokens=raw.budget_tokens,
                exclude=raw.exclude,
                exclude_from_spec=raw.exclude_from_spec,
                mode=raw.mode,
                think=raw.think,
                include=raw.include,
            )
        return raw
    return reasoning_settings_from_entry(
        {"reasoning": raw, "reasoning_effort": effort} if raw is not None or effort else None
    )


def reasoning_settings_from_manifest(
    manifest: dict[str, Any] | None,
    *,
    model: str | None = None,
) -> ReasoningSettings:
    from mas.runtime.engine.llm_request import resolve_model_context

    entry, fallback, name = resolve_model_context(manifest, model=model)
    return reasoning_settings_from_entry(entry, fallback=fallback, model=name)


def reasoning_settings_from_entry(
    entry: dict[str, Any] | None,
    *,
    fallback: dict[str, Any] | None = None,
    model: str | None = None,
) -> ReasoningSettings:
    block, exclude_from_spec = _reasoning_block(entry)
    if not block:
        block, exclude_from_spec = _reasoning_block(fallback)
    effort = _norm_effort(block.get("effort"))
    if not effort:
        effort = _norm_effort((entry or {}).get("reasoning_effort")) or _norm_effort(
            (fallback or {}).get("reasoning_effort")
        )
    budget = _opt_int(block.get("budget_tokens"))
    if budget is None:
        budget = _opt_int((entry or {}).get("reasoning_tokens"))
    exclude = True
    if "exclude" in block:
        exclude = block.get("exclude") is not False
        exclude_from_spec = True
    think = _norm_think(block.get("think")) if "think" in block else None
    include = _norm_include(block.get("include"))
    mode = _norm_mode(block.get("mode"))
    name = model or (entry or {}).get("model") or (fallback or {}).get("model")
    if name:
        from mas.runtime.engine.llm_model_catalog import default_model_catalog

        info = default_model_catalog().get(str(name))
        if info is not None:
            if not effort:
                effort = _norm_effort(info.defaults.get("reasoning.effort"))
            if budget is None:
                budget = _opt_int(info.defaults.get("reasoning.budget_tokens"))
            if think is None and "think" in info.defaults:
                think = _norm_think(info.defaults.get("think"))
            if mode is None:
                mode = _norm_mode(info.defaults.get("reasoning.mode"))
    return ReasoningSettings(
        effort=effort,
        budget_tokens=budget,
        exclude=exclude,
        exclude_from_spec=exclude_from_spec,
        mode=mode,
        think=think,
        include=include,
    )


def apply_reasoning_payload(
    payload: dict[str, Any],
    settings: ReasoningSettings,
    *,
    max_tokens: int | None,
    model: str | None = None,
) -> dict[str, Any]:
    """Mutate a Chat Completions body with portable reasoning fields.

    Unknown models keep every spec field. Known catalog entries omit
    settings the backend does not advertise (so Azure does not 400 on
    ``reasoning``).
    """
    from mas.runtime.engine.llm_model_catalog import default_model_catalog

    info = default_model_catalog().get(model or payload.get("model"))

    def allow(name: str) -> bool:
        return info is None or info.supports(name)

    out = dict(payload)
    if settings.effort and allow("reasoning.effort"):
        out["reasoning_effort"] = settings.effort
    nested: dict[str, Any] = {}
    if settings.budget_tokens is not None and allow("reasoning.budget_tokens"):
        budget = settings.budget_tokens
        if info is not None:
            clamped = info.clamp("reasoning.budget_tokens", budget)
            budget = int(clamped) if isinstance(clamped, (int, float)) and not isinstance(clamped, bool) else budget
        nested["max_tokens"] = budget
    if settings.exclude_from_spec and allow("reasoning.exclude"):
        nested["exclude"] = settings.exclude
    if settings.mode and allow("reasoning.mode"):
        nested["mode"] = settings.mode
    if nested:
        out["reasoning"] = nested
    if settings.think is not None and allow("think"):
        if info is not None and info.defaults.get("think.chat_template_kwargs"):
            extra = dict(out.get("extra_body") or {})
            kwargs = dict(extra.get("chat_template_kwargs") or {})
            kwargs["enable_thinking"] = settings.think is not False
            if isinstance(settings.think, str):
                kwargs["thinking_level"] = settings.think
            extra["chat_template_kwargs"] = kwargs
            out["extra_body"] = extra
        else:
            out["think"] = settings.think
    if settings.include and allow("include"):
        out["include"] = list(settings.include)
    sent_thinking = "reasoning_effort" in out or out.get("think") not in (None, False)
    extra_body = out.get("extra_body") if isinstance(out.get("extra_body"), dict) else {}
    nested_kwargs = extra_body.get("chat_template_kwargs") if isinstance(extra_body, dict) else None
    if isinstance(nested_kwargs, dict) and nested_kwargs.get("enable_thinking"):
        sent_thinking = True
    if _use_max_completion_tokens(info, settings, sent_thinking):
        # o-series / GPT-5 Chat Completions reject max_tokens; they bill
        # hidden reasoning against max_completion_tokens instead.
        if max_tokens is not None:
            out["max_completion_tokens"] = int(max_tokens)
        out.pop("max_tokens", None)
    return out


def _use_max_completion_tokens(info: Any, settings: ReasoningSettings, sent_thinking: bool) -> bool:
    if not (sent_thinking and settings.thinking_enabled()):
        return False
    if info is None:
        return bool(settings.effort) and settings.effort not in _DISABLED_EFFORTS
    return (
        bool(settings.effort)
        and settings.effort not in _DISABLED_EFFORTS
        and info.supports("reasoning.effort")
        and info.supports("reasoning.max_completion_tokens")
    )


def sanitize_assistant_message(
    message: dict[str, Any],
    *,
    exclude: bool = True,
) -> dict[str, Any]:
    """Drop chain-of-thought fields and ``<think>`` blocks from the message."""
    if not exclude or not isinstance(message, dict):
        return message
    out = dict(message)
    for key in _REASONING_MESSAGE_KEYS:
        out.pop(key, None)
    content = out.get("content")
    if isinstance(content, str) and content:
        out["content"] = _THINK_BLOCK_RE.sub("", content).strip() or None
    return out


class ThinkTagStreamFilter:
    """Drop ``<think>`` / ``<thinking>`` spans from streamed content deltas."""

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buf += text
        emitted: list[str] = []
        while self._buf:
            if self._in_think:
                close = _THINK_CLOSE_RE.search(self._buf)
                if close is None:
                    # Keep a short tail in case a close tag is split across chunks.
                    if len(self._buf) > 16:
                        self._buf = self._buf[-16:]
                    return "".join(emitted)
                self._buf = self._buf[close.end() :]
                self._in_think = False
                continue
            open_m = _THINK_OPEN_RE.search(self._buf)
            if open_m is None:
                keep, rest = _split_partial_open_tag(self._buf)
                emitted.append(keep)
                self._buf = rest
                break
            emitted.append(self._buf[: open_m.start()])
            self._buf = self._buf[open_m.end() :]
            self._in_think = True
        return "".join(emitted)


def _reasoning_block(entry: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    if not isinstance(entry, dict):
        return {}, False
    raw = entry.get("reasoning")
    if isinstance(raw, dict):
        return dict(raw), "exclude" in raw
    if isinstance(raw, str) and raw.strip():
        return {"effort": raw.strip()}, False
    return {}, False


def _norm_effort(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text not in _EFFORT_SET:
        raise ValueError(f"unsupported reasoning.effort {value!r}; expected one of {', '.join(REASONING_EFFORTS)}")
    return text


def _norm_mode(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text not in _REASONING_MODES:
        raise ValueError(f"unsupported reasoning.mode {value!r}; expected standard or pro")
    return text


def _norm_think(value: Any) -> bool | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "on"}:
        return True
    if text in {"false", "no", "off"}:
        return False
    if text in {"low", "medium", "high"}:
        return text
    raise ValueError(f"unsupported reasoning.think {value!r}; expected bool or low|medium|high")


def _norm_include(value: Any) -> tuple[str, ...] | None:
    if value is None or value is False:
        return None
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, (list, tuple)):
        items = tuple(str(v).strip() for v in value if str(v).strip())
        return items or None
    raise ValueError(f"unsupported reasoning.include {value!r}; expected list of strings")


def _opt_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    return int(value)


def _split_partial_open_tag(buf: str) -> tuple[str, str]:
    idx = buf.rfind("<")
    if idx >= 0 and _could_be_think_open(buf[idx:]):
        return buf[:idx], buf[idx:]
    return buf, ""


def _could_be_think_open(fragment: str) -> bool:
    lowered = fragment.lower()
    if lowered.startswith("<think"):
        return True
    return "<think>".startswith(lowered) or "<thinking>".startswith(lowered)
