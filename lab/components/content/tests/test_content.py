#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas-lab-content: parser, renderer, widget registry, and export."""

from __future__ import annotations

from mas.lab.content import (
    ContentBlock,
    parse_content,
    render_html,
)
from mas.lab.content.export import export_standalone
from mas.lab.content.renderer import render_markdown_with_widgets
from mas.lab.content.widgets import list_widgets, render_widget


# ── parser ────────────────────────────────────────────────────────────────

def test_parse_plain_text_is_single_text_block():
    blocks = parse_content("hello world")
    assert blocks == [ContentBlock(kind="text", body="hello world")]


def test_parse_widget_directive_with_attrs():
    md = ':::note{variant="warning" title="Heads up"}\nbe careful\n:::'
    blocks = parse_content(md)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.kind == "note"
    assert block.body == "be careful"
    assert block.attrs == {"variant": "warning", "title": "Heads up"}


def test_parse_mixed_text_and_widget_preserves_order():
    md = "intro\n:::note\ninner\n:::\noutro"
    blocks = parse_content(md)
    kinds = [b.kind for b in blocks]
    assert kinds == ["text", "note", "text"]
    assert blocks[0].body == "intro"
    assert blocks[1].body == "inner"
    assert blocks[2].body == "outro"


def test_parse_directive_without_attrs_has_empty_attrs():
    blocks = parse_content(":::mermaid\ngraph TD; A-->B\n:::")
    assert blocks[0].kind == "mermaid"
    assert blocks[0].attrs == {}


def test_parse_trailing_whitespace_only_text_is_dropped():
    # A directive followed by only blank lines should not yield a trailing text block.
    blocks = parse_content(":::note\nx\n:::\n   \n")
    assert [b.kind for b in blocks] == ["note"]


# ── renderer ──────────────────────────────────────────────────────────────

def test_render_text_block_is_prose_div_and_escapes():
    html = render_html([ContentBlock(kind="text", body='a <b> & "c"')])
    assert 'class="prose"' in html
    assert "&lt;b&gt;" in html
    assert "&amp;" in html
    assert "&quot;" in html


def test_render_note_widget_emits_note_markup():
    html = render_html([ContentBlock(kind="note", body="hi", attrs={"variant": "tip"})])
    assert "w-note" in html


def test_render_markdown_with_widgets_roundtrip():
    html = render_markdown_with_widgets("text\n:::note\nbody\n:::")
    assert 'class="prose"' in html
    assert "w-note" in html


# ── widget registry ───────────────────────────────────────────────────────

def test_builtin_widgets_registered():
    widgets = list_widgets()
    for name in ("note", "mermaid", "chart", "code", "figure", "quote"):
        assert name in widgets


def test_unknown_widget_falls_back_to_labeled_block():
    html = render_widget("does-not-exist", "payload <x>", {})
    assert "widget-unknown" in html
    assert "does-not-exist" in html
    # body is HTML-escaped in the fallback
    assert "&lt;x&gt;" in html


# ── export ────────────────────────────────────────────────────────────────

def test_export_standalone_returns_complete_html():
    html = export_standalone("# Title\n\nSome body text.\n", title="Demo")
    assert isinstance(html, str)
    assert "<html" in html.lower()
    assert "Demo" in html
