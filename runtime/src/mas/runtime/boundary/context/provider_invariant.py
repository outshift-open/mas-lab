#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Provider payload invariant helpers for tests and offline validation.

The kernel does not repair violations at assembly time; registered plugins
must produce correct payloads. Use these helpers in unit tests and benches.
"""

from __future__ import annotations

from typing import Any


def tool_call_pairs(messages: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """Return (declared tool_call ids, tool-result ids)."""
    declared = {str(c["id"]) for m in messages if m.get("tool_calls") for c in m["tool_calls"] if c.get("id")}
    returned = {str(m["tool_call_id"]) for m in messages if m.get("role") == "tool" and m.get("tool_call_id")}
    return declared, returned


def assert_provider_payload(messages: list[dict[str, Any]]) -> None:
    """Every tool result must reference a declared tool_call id."""
    declared, returned = tool_call_pairs(messages)
    orphan = returned - declared
    assert not orphan, f"orphan tool results: {orphan}"
