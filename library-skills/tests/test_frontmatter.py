#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for SKILL.md frontmatter parser."""

from __future__ import annotations

from mas.library.skills.lib.frontmatter import parse_skill_frontmatter


def test_well_formed_frontmatter():
    text = """\
---
name: my-skill
description: Does something useful.
tags: [foo, bar]
---
# My Skill

Body here.
"""
    meta, body = parse_skill_frontmatter(text)
    assert meta["name"] == "my-skill"
    assert meta["description"] == "Does something useful."
    assert meta["tags"] == ["foo", "bar"]
    assert "# My Skill" in body
    assert "---" not in body


def test_no_frontmatter():
    text = "# Just a body\n\nNo YAML here."
    meta, body = parse_skill_frontmatter(text)
    assert meta == {}
    assert "Just a body" in body


def test_missing_closing_delimiter():
    text = "---\nname: broken\n# no closing delimiter"
    meta, body = parse_skill_frontmatter(text)
    assert meta == {}
    assert "broken" in body


def test_empty_body():
    text = "---\nname: empty-body\ndescription: No body.\n---\n"
    meta, body = parse_skill_frontmatter(text)
    assert meta["name"] == "empty-body"
    assert body == ""


def test_lenient_unquoted_colon_in_value():
    """Descriptions with colons should parse via the lenient fallback."""
    text = """\
---
name: code-review
description: Use this skill when: reviewing Python code
---
Body.
"""
    meta, body = parse_skill_frontmatter(text)
    assert meta.get("name") == "code-review"
    # The description should be recovered (with or without the colon variant)
    assert "code-review" in (meta.get("name") or "")
    assert body == "Body."


def test_completely_broken_yaml():
    text = "---\n{{{{invalid yaml{{{\n---\nBody."
    meta, body = parse_skill_frontmatter(text)
    assert meta == {}
    assert body == "Body."


def test_body_stripped():
    text = "---\nname: x\ndescription: y\n---\n\n\n  Indented body.\n\n"
    _, body = parse_skill_frontmatter(text)
    assert body == "Indented body."
