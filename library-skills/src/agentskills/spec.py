#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill manifest spec reader — parse skill refs from an agent manifest dict.

This is the only place that knows about the agent manifest structure.
It reads ``spec.context_manager.skills`` (preferred) or the legacy
``spec.skills`` key.

No runtime import is needed — this is pure dict parsing.
"""

from __future__ import annotations


def skill_refs_from_manifest(manifest: dict | None) -> list[str]:
    """Return the list of skill refs declared in the agent manifest spec.

    Reads from ``spec.context_manager.skills`` (preferred) or ``spec.skills``
    (legacy fallback).  Returns an empty list when no skills are declared.
    """
    if not manifest:
        return []
    spec = manifest.get("spec") or {}
    cm = spec.get("context_manager") or {}
    skills = cm.get("skills")
    if skills is None:
        skills = spec.get("skills")
    if not skills:
        return []
    if isinstance(skills, list):
        return [str(s) for s in skills if s]
    return []
