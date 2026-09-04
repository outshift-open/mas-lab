#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SKILL.md frontmatter parser — progressive disclosure tier 1/2 boundary.

A SKILL.md file has two parts:
- YAML frontmatter between ``---`` delimiters (name, description, tags, …)
- A Markdown body after the closing ``---``

The catalog plugin reads only the frontmatter; the activate_skill tool returns
the body (stripping frontmatter) wrapped in <skill_content> tags.
"""

from __future__ import annotations

import logging
import re

import yaml

logger = logging.getLogger(__name__)


def parse_skill_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns ``(metadata_dict, body_text)`` where *body_text* is the Markdown
    content after the closing ``---``, stripped of leading/trailing whitespace.

    Handles:
    - Missing frontmatter: returns ``({}, text)``
    - Malformed YAML (e.g. unquoted values containing colons): falls back to
      quoting suspicious values before retrying, improving cross-client compat
    - Completely unparseable YAML: returns ``({}, text)`` and logs a warning
    """
    if not text.startswith("---"):
        return {}, text.strip()

    # Find the closing --- after the opening one
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text.strip()

    yaml_block = text[3:end].strip()
    body = text[end + 4:].strip()

    meta = _parse_yaml_block(yaml_block)
    return meta, body


def _parse_yaml_block(yaml_block: str) -> dict:
    """Try to parse the YAML block, with a lenient fallback for unquoted colons."""
    try:
        result = yaml.safe_load(yaml_block)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        pass

    # Fallback: wrap bare values that contain colons (common in descriptions)
    # e.g.  description: Use this when: the user asks
    #       → description: "Use this when: the user asks"
    fixed = re.sub(
        r'^(\s*[\w-]+):\s+([^\'"{\[|>][^\n]*:[^\n]*)$',
        lambda m: f'{m.group(1)}: "{m.group(2).strip()}"',
        yaml_block,
        flags=re.MULTILINE,
    )
    try:
        result = yaml.safe_load(fixed)
        if isinstance(result, dict):
            logger.debug("Skill frontmatter: used lenient YAML fallback")
            return result
    except yaml.YAMLError:
        pass

    logger.warning("Skill frontmatter: YAML unparseable, ignoring metadata")
    return {}
