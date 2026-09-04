#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for shared LLM cache helpers and cache modes."""

from __future__ import annotations

from mas.runtime.engine.llm_cache import (
    assistant_message_from_cache_content,
    llm_cache_key,
    resolve_cache_path,
)
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.schema.egress import InvokeEngineIo


def test_resolve_cache_path_prefers_explicit_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("MAS_LLM_CACHE", str(tmp_path / "env-cache.json"))
    explicit = tmp_path / "explicit-cache.json"
    assert resolve_cache_path(explicit) == explicit.resolve()


def test_resolve_cache_path_falls_back_to_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    env_path = tmp_path / "env-cache.json"
    monkeypatch.setenv("MAS_LLM_CACHE", str(env_path))
    assert resolve_cache_path() == env_path.resolve()


def test_resolve_cache_path_defaults_under_shared_xdg_cache_root(tmp_path, monkeypatch):
    """Same $XDG_CACHE_HOME/mas root as the trace/artifacts caches (mas.runtime.xdg)."""
    monkeypatch.delenv("MAS_LLM_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert resolve_cache_path() == tmp_path / "mas" / "llm_cache.json"


def test_llm_cache_key_includes_tools():
    messages = [{"role": "user", "content": "hi"}]
    without_tools = llm_cache_key("mock", messages, None)
    with_tools = llm_cache_key(
        "mock",
        messages,
        [{"type": "function", "function": {"name": "tool-a"}}],
    )
    assert without_tools != with_tools


def test_assistant_message_from_cache_content_parses_tool_calls():
    raw = '{"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}]}'
    msg = assistant_message_from_cache_content(raw)
    assert msg is not None
    assert msg["content"] is None
    assert msg["tool_calls"][0]["function"]["name"] == "t"


def test_live_llm_cache_write_only_persists_without_reading(tmp_path) -> None:
    cache_path = tmp_path / "llm-cache.json"
    engine = LiveLlmEngine(cache_path=cache_path, use_cache=True, cache_read=False, cache_write=True)

    ret = engine._message_to_engine_return(
        InvokeEngineIo(correlation_id=1, op="LLM_CALL"),
        {"role": "assistant", "content": "fresh-response"},
        [{"role": "user", "content": "hi"}],
        [],
        False,
        {},
        "stop",
    )

    assert ret.text == "fresh-response"
    assert cache_path.is_file()
    second = LiveLlmEngine(cache_path=cache_path, use_cache=True, cache_read=False, cache_write=True)
    assert second._cache == {}


def test_live_llm_cache_read_only_loads_existing_cache(tmp_path) -> None:
    cache_path = tmp_path / "llm-cache.json"
    writer = LiveLlmEngine(cache_path=cache_path, use_cache=True, cache_read=False, cache_write=True)
    writer._message_to_engine_return(
        InvokeEngineIo(correlation_id=1, op="LLM_CALL"),
        {"role": "assistant", "content": "cached-response"},
        [{"role": "user", "content": "hello"}],
        [],
        False,
        {},
        "stop",
    )

    reader = LiveLlmEngine(cache_path=cache_path, use_cache=True, cache_read=True, cache_write=False)
    assert reader._cache


def test_live_llm_cache_persists_tool_calls(tmp_path) -> None:
    cache_path = tmp_path / "llm-cache.json"
    engine = LiveLlmEngine(cache_path=cache_path, use_cache=True, cache_read=False, cache_write=True, use_tool_loop=True)

    ret = engine._message_to_engine_return(
        InvokeEngineIo(correlation_id=2, op="LLM_CALL"),
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "demo_tool", "arguments": "{}"},
                }
            ],
        },
        [{"role": "user", "content": "hi"}],
        [{"type": "function", "function": {"name": "demo_tool"}}],
        False,
        {"total_tokens": 12},
        "tool_calls",
    )

    assert ret.next_step == "TOOL_CALL"
    reader = LiveLlmEngine(cache_path=cache_path, use_cache=True, cache_read=True, cache_write=False)
    assert reader._cache
