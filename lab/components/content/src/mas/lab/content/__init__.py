#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.lab.content — Shared content engine for tutorials, articles, and slides.

Provides:
- Widget directive parser (:::widget syntax in markdown)
- Widget registry (chart, mermaid, note, artifact, timeline, etc.)
- Shared CSS theme (Outshift brand)
- Content file resolution (external .md references)
- Static export: standalone HTML or Pelican blog post

Usage:
    from mas.lab.content import parse_content, render_html
    from mas.lab.content.export import export_standalone, export_pelican
    from mas.lab.content.widgets import registry
"""

from mas.lab.content.parser import parse_content, ContentBlock
from mas.lab.content.renderer import render_html
from mas.lab.content.export import export_standalone, export_pelican

__all__ = ["parse_content", "render_html", "ContentBlock", "export_standalone", "export_pelican"]
