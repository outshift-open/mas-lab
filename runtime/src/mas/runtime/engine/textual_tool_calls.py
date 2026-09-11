#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Fallback recovery for models that emit tool calls inside message content.

Some local OpenAI-compatible backends return tool calls as plain assistant text
(`<|tool_call>call:fn(args)<tool_call|>`, bare `name(args)`, multiline JSON, ...)
instead of the structured ``tool_calls`` field. This module is opt-in recovery
used by ``LiveLlmEngine`` only when structured tool calls are absent.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

_TEXT_TOOL_CALL_RE = re.compile(
    r"^\s*call:(?P<name>[A-Za-z0-9_.-]+)\((?P<args>.*)\)\s*$",
    re.DOTALL,
)
_BARE_TOOL_CALL_RE = re.compile(r"^\s*(?:-\s*)?(?P<name>[A-Za-z0-9_.-]+)\((?P<args>.*)\)\s*$")
_BARE_CALL_HEAD_RE = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\(")
_TEXT_TOOL_CALL_BLOCK_RE = re.compile(r"<\|tool_call>(.*?)<tool_call\|>", re.DOTALL)
_CHANNEL_MARKUP_RE = re.compile(r"<\|channel>[^\n<]*\n?(?:<channel\|>)?", re.DOTALL)
_TEXT_VAR_RE = re.compile(r"^\s*(?:-\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.+?)\s*$")
_MERGED_ARG_KEY_RE = re.compile(
    r"^(?P<first_key>[A-Za-z_][A-Za-z0-9_]*)=(?P<first_value>.*),(?P<second_key>[A-Za-z_][A-Za-z0-9_]*)$",
    re.DOTALL,
)


def repair_merged_arg_keys(args: dict[str, Any]) -> dict[str, Any]:
    """Undo a malformed structured tool-call arguments dict from some local models.

    For array-typed parameters (e.g. run_skill_script's ``args``) a backend may
    emit valid-but-wrong JSON: ``{"args=[...]" : "runner.py", ...}`` instead of
    ``{"args": [...], "script": "runner.py", ...}`` -- the array literal ends up
    as text glued onto the START of the key that should have followed it.
    ``json.loads`` succeeds (it is syntactically valid JSON), so this must be
    repaired after parsing, not caught as a decode error.
    """
    repaired: dict[str, Any] = {}
    for key, value in args.items():
        match = _MERGED_ARG_KEY_RE.match(key)
        if not match:
            repaired[key] = value
            continue
        try:
            first_value: Any = json.loads(match.group("first_value"))
        except json.JSONDecodeError:
            first_value = match.group("first_value")
        repaired[match.group("first_key")] = first_value
        repaired[match.group("second_key")] = value
    return repaired


def strip_channel_markup(text: str | None) -> str:
    return _CHANNEL_MARKUP_RE.sub("", str(text or "")).strip()


def recover_tool_calls_from_content(
    content: str | None,
    *,
    known_tool_names: set[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Recover structured tool calls from message content, plus the leftover text."""
    raw = str(content or "")
    cleaned = strip_channel_markup(raw)
    blocks = _TEXT_TOOL_CALL_BLOCK_RE.findall(raw)
    variables = _collect_text_variables(cleaned)
    tool_calls: list[dict[str, Any]] = []

    for idx, item in enumerate(blocks or ([raw] if cleaned.startswith("call:") else []), start=1):
        match = _TEXT_TOOL_CALL_RE.match(item.strip())
        if match:
            args = _parse_textual_tool_call_args(match.group("args"), variables=variables)
            tool_calls.append(_as_tool_call(idx, match.group("name"), args))

    if not tool_calls:
        for line in cleaned.splitlines():
            match = _BARE_TOOL_CALL_RE.match(line.strip())
            if match:
                args = _parse_textual_tool_call_args(match.group("args"), variables=variables)
                tool_calls.append(_as_tool_call(len(tool_calls) + 1, match.group("name"), args))

    if not tool_calls and known_tool_names:
        spans: list[tuple[int, int]] = []
        for name, args_raw, start, end in _find_multiline_bare_calls(cleaned, known_names=known_tool_names):
            args = _parse_textual_tool_call_args(args_raw, variables=variables)
            tool_calls.append(_as_tool_call(len(tool_calls) + 1, name, args))
            spans.append((start, end))
        for start, end in sorted(spans, reverse=True):
            cleaned = (cleaned[:start] + cleaned[end:]).strip()

    if blocks:
        cleaned = _TEXT_TOOL_CALL_BLOCK_RE.sub("", cleaned).strip()
    if tool_calls and cleaned.startswith("call:"):
        cleaned = ""
    return tool_calls, cleaned


def maybe_recover_textual_tool_calls(
    message: dict[str, Any],
    tool_defs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply textual tool-call recovery when the assistant message has no structured calls."""
    if message.get("tool_calls"):
        return message

    known_tool_names = {
        str(fn.get("name"))
        for t in tool_defs
        if isinstance(t, dict) and isinstance(fn := t.get("function"), dict) and fn.get("name")
    }
    tool_calls, recovered_text = recover_tool_calls_from_content(
        message.get("content"),
        known_tool_names=known_tool_names,
    )
    # Strip channel markup even when no tool call was recovered -- some backends
    # emit it on plain answers too, and it must never reach the user.
    return {**message, "tool_calls": tool_calls, "content": recovered_text}


def _parse_textual_tool_call_args(
    raw: str,
    *,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variables = variables or {}
    stripped = raw.strip()
    if stripped and "=" not in stripped and ":" not in stripped and stripped in variables:
        return {"value": variables[stripped]}

    payload = raw.replace('<|"|>', '"').strip()
    if not payload:
        return {}
    for name, value in variables.items():
        payload = re.sub(rf"\b{re.escape(name)}\b", json.dumps(value), payload)
    payload = payload.replace("=", ":")
    payload = re.sub(
        r"(^|[,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:",
        lambda m: f'{m.group(1)}"{m.group(2)}": ',
        payload,
    )
    if not payload.startswith("{"):
        payload = "{" + payload + "}"
    try:
        loaded = yaml.safe_load(payload)
    except Exception:
        return {"raw": raw}
    return dict(loaded) if isinstance(loaded, dict) else {"raw": raw}


def _collect_text_variables(content: str) -> dict[str, Any]:
    """``name_raw: <json>`` lines the model emits before referencing them by name."""
    variables: dict[str, Any] = {}
    for line in content.splitlines():
        match = _TEXT_VAR_RE.match(line)
        if not match or not match.group("name").endswith("_raw"):
            continue
        value_text = match.group("value").strip()
        try:
            variables[match.group("name")] = json.loads(value_text)
        except Exception:
            variables[match.group("name")] = value_text.strip('"')
    return variables


def _as_tool_call(index: int, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"text-tool-call-{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, sort_keys=True)},
    }


def _find_multiline_bare_calls(text: str, *, known_names: set[str]) -> list[tuple[str, str, int, int]]:
    """Find ``name(...)`` calls whose arguments span multiple lines.

    ``_BARE_TOOL_CALL_RE`` only matches a call that is a whole physical line,
    which misses models that write a tool call as pretty-printed JSON args across
    several lines, e.g. ``run_skill_script({\n  "skill": ...\n})``.
    Restricted to declared tool names so this never mistakes prose like
    "the discount (25%)" for a call.
    """
    calls: list[tuple[str, str, int, int]] = []
    for match in _BARE_CALL_HEAD_RE.finditer(text):
        name = match.group("name")
        if name not in known_names:
            continue
        depth = 1
        i = match.end()
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        if depth == 0:
            calls.append((name, text[match.end() : i - 1], match.start(), i))
    return calls
