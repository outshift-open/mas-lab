#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill manifest spec reader — parse skill refs from an agent manifest dict.

This is the only place in library-skills that knows about the agent manifest
structure.  It reads ``spec.skills``.

No runtime import is needed — this is pure dict parsing.
"""

from __future__ import annotations


def skill_refs_from_manifest(manifest: dict | None) -> list[str]:
    """Return the list of skill refs declared in the agent manifest spec.

    Reads from ``spec.skills``.  Returns an empty list when no skills are
    declared.
    """
    if not manifest:
        return []
    spec = manifest.get("spec") or {}
    skills = spec.get("skills")
    if not skills:
        return []
    if isinstance(skills, list):
        return [str(s) for s in skills if s]
    return []
