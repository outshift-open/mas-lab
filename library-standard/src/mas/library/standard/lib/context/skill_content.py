#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Keep activated skill content out of history compaction.

Agent Skills (agentskills.io, Step 5): skill instructions are durable
guidance, so a context manager that summarizes or drops older turns must not
prune them. Skill content is identified by the ``<skill_content name="…">``
wrapper that ``activate_skill`` returns, so this module does not import
library-skills.

A folded prefix keeps each skill's latest block as its own ``system`` row,
and the summarizer only sees a short stub in place of the tool result.
"""

from __future__ import annotations

import json
import re
from typing import Any

_BLOCK = re.compile(r'<skill_content name="([^"]+)">.*?</skill_content>', re.S)
_PINNED = re.compile(r'<activated_skill name="([^"]+)">')


def _skill_text(msg: dict[str, Any]) -> str:
    content = msg.get("content")
    if not isinstance(content, str) or "<skill_content" not in content:
        return ""
    role = msg.get("role")
    if role == "tool":
        try:
            data = json.loads(content)
        except ValueError:
            return content
        inner = data.get("content") if isinstance(data, dict) else None
        return inner if isinstance(inner, str) else content
    if role == "system":
        return content
    return ""


def skill_blocks(msg: dict[str, Any]) -> list[tuple[str, str]]:
    """``(name, block)`` for each ``<skill_content>`` in a tool or system row."""
    return [(m.group(1), m.group(0)) for m in _BLOCK.finditer(_skill_text(msg))]


def is_skill_block(msg: dict[str, Any]) -> bool:
    """True for a ``system`` row that holds only retained skill content."""
    if msg.get("role") != "system":
        return False
    content = str(msg.get("content") or "").strip()
    return content.startswith("<skill_content") and content.endswith("</skill_content>")


def split_skill_content(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a prefix about to be folded into ``(rest, retained)``.

    ``retained`` holds one ``system`` row per skill, latest activation wins.
    ``rest`` replaces skill tool results with a stub (pairing stays intact)
    and drops rows that :func:`is_skill_block` already retained.
    """
    found: dict[str, str] = {}
    rest: list[dict[str, Any]] = []
    for msg in messages:
        blocks = skill_blocks(msg)
        if not blocks:
            rest.append(msg)
            continue
        for name, block in blocks:
            found[name] = block
        if msg.get("role") == "tool":
            names = ", ".join(name for name, _ in blocks)
            rest.append({**msg, "content": f"[skill content retained verbatim: {names}]"})
        elif not is_skill_block(msg):
            rest.append(msg)
    retained = [{"role": "system", "content": block} for block in found.values()]
    return rest, retained


def drop_pinned_skill_blocks(
    messages: list[dict[str, Any]],
    system_text: str,
) -> list[dict[str, Any]]:
    """Drop retained blocks for skills the system prompt already pins."""
    pinned = set(_PINNED.findall(system_text or ""))
    if not pinned:
        return messages
    return [
        msg
        for msg in messages
        if not (is_skill_block(msg) and {name for name, _ in skill_blocks(msg)} <= pinned)
    ]
