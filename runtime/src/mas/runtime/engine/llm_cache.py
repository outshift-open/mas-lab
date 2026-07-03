#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared LLM response cache utilities (live engine, mock model access, HTTP mock server)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def resolve_cache_path(cache_path: str | Path | None = None) -> Path:
    if cache_path:
        return Path(cache_path).expanduser().resolve()
    env = os.environ.get("MAS_LLM_CACHE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return (base / "mas" / "llm_cache.json").resolve()


def load_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def persist_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def llm_cache_key(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> str:
    blob = json.dumps(
        {"model": model, "messages": messages, "tools": tools or []},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def lookup_response(
    cache: dict[str, Any],
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str | None, dict[str, Any] | None, str]:
    """Return ``(content, usage, source)`` for a cached completion, if any."""
    key = llm_cache_key(model, messages, tools)
    entry = cache.get(key)
    if isinstance(entry, str) and entry.strip():
        return entry, None, "cache"
    if isinstance(entry, dict):
        content = entry.get("content")
        usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else None
        if isinstance(content, str) and content.strip():
            return content, usage, str(entry.get("source") or "cache")
        tool_calls = entry.get("tool_calls")
        if tool_calls:
            return json.dumps({"tool_calls": tool_calls}), usage, "cache"
    return None, None, ""


def last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""


def assistant_message_from_cache_content(content: str | None) -> dict[str, Any] | None:
    """Parse a cache entry into an OpenAI-shaped assistant message."""
    if not content or not str(content).strip():
        return None
    text = str(content)
    if not text.startswith("{"):
        return {"role": "assistant", "content": text}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"role": "assistant", "content": text}
    if isinstance(parsed, dict) and parsed.get("tool_calls"):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": parsed["tool_calls"],
        }
    return {"role": "assistant", "content": text}
