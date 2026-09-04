#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""agentskills.io client library — skill discovery, parsing, lifecycle."""

from .discovery import Discovery
from .lifecycle import ActivatedSkill, SkillSessionState
from .parsing import parse_skill_frontmatter
from .registry import SkillRecord, SkillRegistry
from .spec import skill_refs_from_manifest

__all__ = [
    "ActivatedSkill",
    "Discovery",
    "SkillRecord",
    "SkillRegistry",
    "SkillSessionState",
    "parse_skill_frontmatter",
    "skill_refs_from_manifest",
]
