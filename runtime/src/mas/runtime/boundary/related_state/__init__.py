#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Related world-state that is NOT Mealy Q.

Coding harnesses treat the execute filesystem as state. Putting file
bytes in ``QProduct`` would grow the kernel without bound. This plugin
stores a *fingerprint and locator* on the snapshot; an adapter (git,
copy, overlayfs, …) owns the bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RelatedStateRef:
    """Pointer to plugin-owned world state. Safe to put on a Snapshot."""

    plugin: str
    fingerprint: str
    locator: str = ""
    adapter: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "plugin": self.plugin,
            "fingerprint": self.fingerprint,
            "locator": self.locator,
            "adapter": self.adapter,
        }

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> RelatedStateRef:
        return cls(
            plugin=str(raw.get("plugin") or ""),
            fingerprint=str(raw.get("fingerprint") or ""),
            locator=str(raw.get("locator") or ""),
            adapter=str(raw.get("adapter") or ""),
        )


class RelatedStatePlugin(Protocol):
    """Capture/restore world state for one session. Never mutates Q."""

    name: str

    def capture(self, session_id: str) -> RelatedStateRef: ...

    def restore(self, session_id: str, ref: RelatedStateRef) -> None: ...


class NullRelatedState:
    """Default: no related filesystem. Chat agents do not need one."""

    name = "none"

    def capture(self, session_id: str) -> RelatedStateRef:
        return RelatedStateRef(plugin=self.name, fingerprint="", adapter="none")

    def restore(self, session_id: str, ref: RelatedStateRef) -> None:
        return None


def capture_all(plugins: list[RelatedStatePlugin] | None, session_id: str) -> list[RelatedStateRef]:
    refs: list[RelatedStateRef] = []
    for plugin in plugins or []:
        ref = plugin.capture(session_id)
        if ref.fingerprint or ref.locator:
            refs.append(ref)
    return refs


def coerce_refs(raw: list[Any] | None) -> list[RelatedStateRef]:
    refs: list[RelatedStateRef] = []
    for item in raw or []:
        if isinstance(item, RelatedStateRef):
            refs.append(item)
        elif isinstance(item, dict):
            refs.append(RelatedStateRef.from_payload(item))
    return refs


def restore_all(plugins: list[RelatedStatePlugin] | None, session_id: str, refs: list[RelatedStateRef] | list[Any] | None) -> None:
    by_name = {p.name: p for p in plugins or []}
    for ref in coerce_refs(list(refs or [])):
        plugin = by_name.get(ref.plugin)
        if plugin is not None:
            plugin.restore(session_id, ref)
