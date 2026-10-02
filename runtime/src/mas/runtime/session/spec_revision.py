#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Live spec: the bound manifest can change, and every change is recorded."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mas.runtime.session.state import ManifestRef

_ALLOWED_DELTAS = frozenset({"materialize", "disable_tool", "set_pattern", "overlay_factor"})


@dataclass(frozen=True)
class SpecDelta:
    kind: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_DELTAS:
            raise ValueError(f"unknown spec delta {self.kind!r}")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SpecDelta":
        extra = sorted(set(data) - {"kind", "payload"})
        if extra:
            raise ValueError(f"unknown spec delta keys {extra}")
        return cls(str(data.get("kind") or ""), dict(data.get("payload") or {}))


@dataclass(frozen=True)
class SpecRevision:
    revision: int
    content_hash: str
    parent_revision: int | None
    actor: str
    reason: str
    delta: SpecDelta
    taken_at: str


class SpecRevisionLog:
    """Per-session spec spine. Restore a snapshot by replaying to that revision."""

    def __init__(self) -> None:
        self._revs: dict[str, list[SpecRevision]] = {}
        self._manifests: dict[str, dict[str, Any]] = {}
        self._heads: dict[str, int] = {}

    def materialize(self, session_id: str, manifest: dict[str, Any], *, actor: str = "bootstrap") -> SpecRevision:
        body = copy.deepcopy(manifest)
        ref = ManifestRef.from_content(body)
        rev = SpecRevision(
            revision=0,
            content_hash=ref.content_hash,
            parent_revision=None,
            actor=actor,
            reason="initial materialization",
            delta=SpecDelta("materialize", {}),
            taken_at=datetime.now(UTC).isoformat(),
        )
        self._revs[session_id] = [rev]
        self._manifests[session_id] = body
        self._heads[session_id] = 0
        return rev

    def current_manifest(self, session_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._manifests[session_id])

    def current_spec(self, session_id: str) -> dict[str, Any]:
        manifest = self._manifests.get(session_id) or {}
        spec = manifest.get("spec")
        return copy.deepcopy(spec) if isinstance(spec, dict) else {}

    def latest(self, session_id: str) -> SpecRevision | None:
        revs = self._revs.get(session_id) or []
        if not revs:
            return None
        head = self._heads.get(session_id)
        if head is None:
            return revs[-1]
        for rev in reversed(revs):
            if rev.revision == head:
                return rev
        return revs[-1]

    def apply(
        self,
        session_id: str,
        delta: SpecDelta,
        *,
        actor: str,
        reason: str,
    ) -> SpecRevision:
        parent = self.latest(session_id)
        if parent is None:
            raise KeyError(f"session {session_id!r} has no materialized spec")
        manifest = copy.deepcopy(self._manifests[session_id])
        spec = manifest.setdefault("spec", {})
        if not isinstance(spec, dict):
            raise ValueError("manifest spec must be an object")
        _apply_delta(spec, delta)
        ref = ManifestRef.from_content(manifest)
        rev = SpecRevision(
            revision=parent.revision + 1,
            content_hash=ref.content_hash,
            parent_revision=parent.revision,
            actor=actor,
            reason=reason,
            delta=delta,
            taken_at=datetime.now(UTC).isoformat(),
        )
        self._revs[session_id].append(rev)
        self._manifests[session_id] = manifest
        self._heads[session_id] = rev.revision
        return rev

    def restore_manifest(self, session_id: str, manifest: dict[str, Any], revision: int) -> None:
        self._manifests[session_id] = copy.deepcopy(manifest)
        self._heads[session_id] = revision

    def clear_session(self, session_id: str) -> None:
        self._revs.pop(session_id, None)
        self._manifests.pop(session_id, None)
        self._heads.pop(session_id, None)


def _apply_delta(spec: dict[str, Any], delta: SpecDelta) -> None:
    if delta.kind == "disable_tool":
        name = str(delta.payload.get("name") or "")
        if not name:
            raise ValueError("disable_tool requires payload.name")
        for tool in spec.get("tools") or []:
            if isinstance(tool, dict) and tool.get("name") == name:
                tool["enabled"] = False
                return
        raise ValueError(f"tool {name!r} is not in the current spec")
    if delta.kind == "set_pattern":
        spec["design_pattern"] = delta.payload.get("pattern")
        return
    if delta.kind == "overlay_factor":
        spec.setdefault("factors", {})
        if not isinstance(spec["factors"], dict):
            raise ValueError("spec.factors must be an object")
        spec["factors"][str(delta.payload.get("id") or "factor")] = delta.payload.get("value")
        return
    if delta.kind == "materialize":
        return
    raise ValueError(f"unknown spec delta {delta.kind!r}")
