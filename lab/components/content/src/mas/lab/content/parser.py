#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Content parser — extracts widget directives from markdown.

Syntax (remark-directive compatible):

    :::chart{src="data.csv" type="line" title="Loss curves"}
    :::

    :::note{variant="info"}
    This is an important note about the pipeline.
    :::

    :::mermaid
    graph LR
      A --> B --> C
    :::

    :::artifact{type="kg" src="results/kg.json"}
    :::

    :::timeline{src="events.json"}
    :::

The parser splits markdown into a sequence of ContentBlocks:
- TextBlock: raw markdown (rendered by marked.js client-side)
- WidgetBlock: directive name + attrs + body (rendered by widget registry)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentBlock:
    """A parsed content block — either prose or a widget directive."""

    kind: str  # "text" | widget name (e.g. "chart", "mermaid", "note")
    body: str = ""  # Markdown text or widget body content
    attrs: dict[str, str] = field(default_factory=dict)


# Regex: matches :::name{key="val" key2="val2"} or :::name (no attrs)
_DIRECTIVE_OPEN = re.compile(
    r'^:::(\w+)(?:\{([^}]*)\})?\s*$'
)
_DIRECTIVE_CLOSE = re.compile(r'^:::\s*$')
_ATTR_PATTERN = re.compile(r'(\w+)=["\']([^"\']*)["\']')


def _parse_attrs(attr_str: str | None) -> dict[str, str]:
    """Parse key="value" pairs from directive attribute string."""
    if not attr_str:
        return {}
    return dict(_ATTR_PATTERN.findall(attr_str))


def parse_content(markdown: str) -> list[ContentBlock]:
    """Parse markdown with widget directives into a block sequence.

    Returns a list of ContentBlock objects. Text blocks contain raw markdown
    that should be rendered client-side by marked.js. Widget blocks contain
    the directive name, attributes, and body content for the widget registry
    to render.
    """
    blocks: list[ContentBlock] = []
    lines = markdown.split("\n")
    text_buf: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = _DIRECTIVE_OPEN.match(line)

        if m:
            # Flush accumulated text
            if text_buf:
                blocks.append(ContentBlock(kind="text", body="\n".join(text_buf)))
                text_buf = []

            widget_name = m.group(1)
            attrs = _parse_attrs(m.group(2))
            body_lines: list[str] = []
            i += 1

            # Collect body until closing :::
            while i < len(lines):
                if _DIRECTIVE_CLOSE.match(lines[i]):
                    i += 1
                    break
                body_lines.append(lines[i])
                i += 1

            blocks.append(ContentBlock(
                kind=widget_name,
                body="\n".join(body_lines),
                attrs=attrs,
            ))
        else:
            text_buf.append(line)
            i += 1

    # Flush remaining text
    if text_buf:
        text = "\n".join(text_buf)
        if text.strip():
            blocks.append(ContentBlock(kind="text", body=text))

    return blocks
