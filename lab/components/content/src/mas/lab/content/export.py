#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Static export — produces self-contained HTML from content markdown.

Two output formats:
1. **standalone**: Full HTML page with all CSS/JS inlined, no external deps.
   Can be opened in a browser directly or served statically.
2. **pelican**: Markdown file with Pelican metadata header + embedded HTML
   widget blocks, plus an accompanying assets/ dir for any data files.

Usage:
    from mas.lab.content.export import export_standalone, export_pelican

    # Standalone HTML (single file, offline)
    html = export_standalone("content.md", title="My Post", mode="article")

    # Pelican blog integration
    export_pelican("content.md", output_dir="~/repos/perso/website/content/blog/2026-05-22-my-post/")
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Literal

from mas.lab.content.parser import parse_content
from mas.lab.content.renderer import render_html

# ---------------------------------------------------------------------------
# CSS & JS — inlined for offline self-contained export
# ---------------------------------------------------------------------------

_THEME_CSS_PATH = Path(__file__).parent / "themes" / "outshift.css"


def _load_theme_css() -> str:
    return _THEME_CSS_PATH.read_text(encoding="utf-8")


# Minimal marked.js substitute for offline — we ship actual marked via CDN fallback
_OFFLINE_JS = """\
/* Offline markdown renderer — uses marked.js from CDN with local fallback */
(function() {
  function renderAllMd() {
    document.querySelectorAll('[data-md]').forEach(function(el) {
      if (window.marked) {
        el.innerHTML = marked.parse(el.getAttribute('data-md'));
      } else {
        // Fallback: show raw markdown in <pre>
        var pre = document.createElement('pre');
        pre.style.whiteSpace = 'pre-wrap';
        pre.textContent = el.getAttribute('data-md');
        el.appendChild(pre);
      }
    });
  }

  function highlightAll() {
    if (window.hljs) {
      document.querySelectorAll('pre code[class*="language-"]').forEach(function(el) {
        hljs.highlightElement(el);
      });
    }
  }

  function renderMermaid() {
    if (window.mermaid) {
      mermaid.initialize({startOnLoad: false, theme: 'dark'});
      document.querySelectorAll('.mermaid').forEach(function(el) {
        mermaid.run({nodes: [el]});
      });
    }
  }

  function renderCharts() {
    document.querySelectorAll('[data-chart]').forEach(function(el) {
      if (!window.Chart) return;
      try {
        var spec = JSON.parse(el.getAttribute('data-chart'));
        new Chart(el.querySelector('canvas') || el, {type: spec.type || 'bar', data: spec.data || spec, options: spec.options || {}});
      } catch(e) { console.warn('Chart render error:', e); }
    });
  }

  // Reading progress bar
  function initProgress() {
    var bar = document.getElementById('reading-progress');
    if (!bar) return;
    window.addEventListener('scroll', function() {
      var h = document.documentElement;
      var pct = (h.scrollTop / (h.scrollHeight - h.clientHeight)) * 100;
      bar.style.width = pct + '%';
    });
  }

  // TOC active tracking
  function initTocTracking() {
    var sections = document.querySelectorAll('[data-toc-id]');
    var links = document.querySelectorAll('.toc-nav a');
    if (!sections.length || !links.length) return;
    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(e) {
        if (e.isIntersecting) {
          links.forEach(function(l) { l.classList.remove('active'); });
          var id = e.target.getAttribute('data-toc-id');
          var link = document.querySelector('.toc-nav a[href="#' + id + '"]');
          if (link) link.classList.add('active');
        }
      });
    }, {rootMargin: '-20% 0px -60% 0px'});
    sections.forEach(function(s) { observer.observe(s); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      renderAllMd(); highlightAll(); renderMermaid(); renderCharts();
      initProgress(); initTocTracking();
    });
  } else {
    renderAllMd(); highlightAll(); renderMermaid(); renderCharts();
    initProgress(); initTocTracking();
  }
})();
"""

# Layout CSS for standalone page (not the widget CSS — that's in outshift.css)
_STANDALONE_LAYOUT_CSS = """\
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--text-body);
  font-family: var(--sans); font-size: 16px; line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}
.page-wrapper {
  display: grid; grid-template-columns: 220px 1fr;
  max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem;
  gap: 3rem; min-height: 100vh;
}
.page-wrapper.no-toc { grid-template-columns: 1fr; max-width: 760px; }

/* TOC sidebar */
.toc-nav {
  position: sticky; top: 2rem; align-self: start;
  max-height: calc(100vh - 4rem); overflow-y: auto;
  padding-right: 1rem; border-right: 1px solid var(--border);
}
.toc-nav h4 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); margin-bottom: 0.8rem; }
.toc-nav ul { list-style: none; padding: 0; margin: 0; }
.toc-nav li { margin-bottom: 0.4rem; }
.toc-nav a {
  font-size: 0.8rem; color: var(--text-dim); text-decoration: none;
  padding: 0.2rem 0.5rem; border-radius: 4px; display: block;
  transition: all 0.2s var(--transition);
}
.toc-nav a:hover { color: var(--text); }
.toc-nav a.active { color: var(--accent); background: rgba(0,212,255,0.06); }

/* Main content area */
.content-main { min-width: 0; }
.content-main > header { margin-bottom: 2.5rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
.content-main > header h1 { font-size: 2rem; font-weight: 800; color: var(--text); margin: 0 0 0.5rem; line-height: 1.2; }
.content-main > header .subtitle { color: var(--text-dim); font-size: 1rem; }
.content-main > header .meta { margin-top: 0.8rem; font-size: 0.78rem; color: var(--text-dim); }
.content-main > header .meta span + span::before { content: '·'; margin: 0 0.5rem; }

/* Reading progress */
.reading-progress {
  position: fixed; top: 0; left: 0; height: 3px; z-index: 100;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  width: 0%; transition: width 0.1s;
}

/* Section separators */
.section-sep { margin: 3rem 0 2rem; border: none; border-top: 1px solid var(--border); }

@media (max-width: 768px) {
  .page-wrapper { grid-template-columns: 1fr; padding: 1rem; gap: 0; }
  .toc-nav { display: none; }
}
"""

# CDN URLs (with integrity) — loaded first, offline JS kicks in regardless
_CDN_DEPS = [
    '<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>',
    '<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/lib/highlight.min.js"></script>',
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github-dark.min.css">',
    '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>',
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>',
]


# ---------------------------------------------------------------------------
# TOC extraction
# ---------------------------------------------------------------------------

def _extract_toc(markdown: str) -> list[dict]:
    """Extract headings from markdown for TOC generation."""
    toc = []
    for match in re.finditer(r'^(#{2,3})\s+(.+)$', markdown, re.MULTILINE):
        level = len(match.group(1))
        title = match.group(2).strip()
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        toc.append({"level": level, "title": title, "slug": slug})
    return toc


def _render_toc_html(toc: list[dict]) -> str:
    if not toc:
        return ""
    parts = ['<nav class="toc-nav"><h4>Contents</h4><ul>']
    for item in toc:
        indent = '  ' if item["level"] > 2 else ''
        cls = ' class="toc-sub"' if item["level"] > 2 else ''
        parts.append(f'{indent}<li{cls}><a href="#{item["slug"]}">{item["title"]}</a></li>')
    parts.append('</ul></nav>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Standalone export
# ---------------------------------------------------------------------------

def export_standalone(
    source: str | Path,
    *,
    title: str = "",
    subtitle: str = "",
    author: str = "",
    date_str: str = "",
    mode: Literal["article", "slides"] = "article",
    include_toc: bool = True,
) -> str:
    """Export a markdown content file to a self-contained HTML page.

    Args:
        source: Path to .md file or raw markdown string.
        title: Page title (extracted from first H1 if empty).
        subtitle: Optional subtitle/description.
        author: Author name.
        date_str: Date string (defaults to today).
        mode: 'article' for scrollable report, 'slides' for future slide mode.
        include_toc: Whether to generate a sidebar TOC.

    Returns:
        Complete HTML string — can be saved to file and opened offline.
    """
    if isinstance(source, Path) or (isinstance(source, str) and not "\n" in source and Path(source).exists()):
        markdown = Path(source).read_text(encoding="utf-8")
    else:
        markdown = source

    # Extract metadata from frontmatter if present
    meta, markdown = _extract_frontmatter(markdown)
    title = title or meta.get("title", "")
    subtitle = subtitle or meta.get("subtitle", meta.get("summary", ""))
    author = author or meta.get("author", "")
    date_str = date_str or meta.get("date", str(date.today()))

    # Auto-extract title from first H1 if not specified
    if not title:
        h1_match = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()
            markdown = markdown[:h1_match.start()] + markdown[h1_match.end():]

    # Parse and render content blocks
    blocks = parse_content(markdown)
    body_html = render_html(blocks)

    # Inject data-toc-id on headings for TOC tracking
    toc = _extract_toc(markdown)
    for item in toc:
        body_html = body_html.replace(
            f'data-md="',
            f'data-toc-id="{item["slug"]}" data-md="',
            1,
        ) if item["slug"] in body_html else body_html

    # TOC
    toc_html = _render_toc_html(toc) if include_toc and toc else ""
    wrapper_cls = "page-wrapper" if toc_html else "page-wrapper no-toc"

    # Meta line
    meta_parts = []
    if author:
        meta_parts.append(f"<span>{author}</span>")
    if date_str:
        meta_parts.append(f"<span>{date_str}</span>")
    meta_html = "\n".join(meta_parts)

    # Assemble
    theme_css = _load_theme_css()
    cdn_html = "\n".join(_CDN_DEPS)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
{cdn_html}
<style>
{theme_css}
{_STANDALONE_LAYOUT_CSS}
</style>
</head>
<body>
<div class="reading-progress" id="reading-progress"></div>
<div class="{wrapper_cls}">
  {toc_html}
  <div class="content-main">
    <header>
      <h1>{_esc(title)}</h1>
      {f'<div class="subtitle">{_esc(subtitle)}</div>' if subtitle else ''}
      <div class="meta">{meta_html}</div>
    </header>
    {body_html}
  </div>
</div>
<script>
{_OFFLINE_JS}
</script>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Pelican export
# ---------------------------------------------------------------------------

def export_pelican(
    source: str | Path,
    output_dir: str | Path,
    *,
    title: str = "",
    slug: str = "",
    category: str = "Research",
    tags: list[str] | None = None,
    lang: str = "en",
    status: str = "draft",
    date_str: str = "",
    author: str = "Jordan Augé",
) -> Path:
    """Export content markdown as a Pelican blog post.

    Creates:
      output_dir/
        index.md       — Pelican article with metadata + rendered HTML
        assets/        — any data files referenced by widgets

    The HTML content uses a <div class="mas-content"> wrapper so the blog
    theme can scope widget styles without conflicts.

    Args:
        source: Path to .md content file or raw markdown.
        output_dir: Target directory (e.g. ~/repos/perso/website/content/blog/2026-05-22-my-post/)
        title: Post title.
        slug: URL slug (auto-generated from title if empty).
        category: Pelican category.
        tags: List of tags.
        lang: Language code.
        status: 'draft' or 'published'.
        date_str: Publication date.
        author: Author name.

    Returns:
        Path to the generated index.md.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(source, Path) or (isinstance(source, str) and not "\n" in source and Path(source).exists()):
        markdown = Path(source).read_text(encoding="utf-8")
    else:
        markdown = source

    # Extract frontmatter
    meta, markdown = _extract_frontmatter(markdown)
    title = title or meta.get("title", "Untitled")
    date_str = date_str or meta.get("date", str(date.today()))
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    # Render content HTML
    blocks = parse_content(markdown)
    content_html = render_html(blocks)

    # Write the widget CSS as a separate file
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    css_file = assets_dir / "mas-content.css"
    css_file.write_text(_load_theme_css(), encoding="utf-8")

    # Build Pelican markdown
    tags_str = ", ".join(tags) if tags else category.lower()
    pelican_md = f"""---
title: {title}
date: {date_str}
slug: {slug}
lang: {lang}
author: {author}
category: {category}
tags: {tags_str}
status: {status}
template: article
extra_css: assets/mas-content.css
---

<!-- MAS Content Export — widget directives rendered as HTML -->
<!-- Interactive elements require marked.js, mermaid.js, highlight.js (loaded by theme or inline) -->

<div class="mas-content">
{content_html}
</div>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/lib/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
{_OFFLINE_JS}
</script>
"""

    index_path = output_dir / "index.md"
    index_path.write_text(pelican_md, encoding="utf-8")
    return index_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_frontmatter(markdown: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown, returning (meta_dict, body)."""
    if not markdown.startswith("---"):
        return {}, markdown
    end = markdown.find("---", 3)
    if end == -1:
        return {}, markdown
    front = markdown[3:end].strip()
    body = markdown[end + 3:].lstrip("\n")
    meta = {}
    for line in front.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta, body


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
