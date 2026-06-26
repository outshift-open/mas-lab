#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Content renderer — converts parsed ContentBlocks to HTML.

Supports two output modes:
- "inline": for embedding in a larger page (returns HTML fragments)
- "full": standalone page with theme CSS + JS deps
"""

from __future__ import annotations

from mas.lab.content.parser import ContentBlock, parse_content
from mas.lab.content.widgets import render_widget


def render_html(blocks: list[ContentBlock]) -> str:
    """Render a list of content blocks to HTML fragments.

    Text blocks are rendered as data-md divs (client-side marked.js).
    Widget blocks are rendered server-side by the widget registry.
    """
    parts = []
    for block in blocks:
        if block.kind == "text":
            escaped = _esc_attr(block.body)
            parts.append(f'<div class="prose" data-md="{escaped}"></div>')
        else:
            parts.append(render_widget(block.kind, block.body, block.attrs))
    return "\n".join(parts)


def render_markdown_with_widgets(markdown: str) -> str:
    """Parse markdown with directives and render to HTML (one-shot)."""
    blocks = parse_content(markdown)
    return render_html(blocks)


def _esc_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
