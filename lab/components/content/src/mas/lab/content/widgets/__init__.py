#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Widget registry — maps directive names to render functions.

Each widget is a function: (body: str, attrs: dict) -> str (HTML)

Built-in widgets:
- note: callout box (info/warning/tip variants)
- mermaid: diagram rendered by mermaid.js
- chart: data visualization (line/bar/scatter) — renders a canvas or embed
- artifact: references a mas-lab artifact (kg, otel, trace)
- timeline: event timeline visualization
- code: syntax-highlighted code block with optional title
- embed: iframe embed (HTML file, Gradio, etc.)
- figure: image with caption and numbering
"""

from __future__ import annotations

from typing import Callable

WidgetFn = Callable[[str, dict[str, str]], str]

_REGISTRY: dict[str, WidgetFn] = {}


def register(name: str):
    """Decorator to register a widget render function."""
    def decorator(fn: WidgetFn) -> WidgetFn:
        _REGISTRY[name] = fn
        return fn
    return decorator


def render_widget(name: str, body: str, attrs: dict[str, str]) -> str:
    """Render a widget by name. Falls back to a code block if unknown."""
    fn = _REGISTRY.get(name)
    if fn:
        return fn(body, attrs)
    # Fallback: render as fenced block with name label
    safe_body = body.replace("&", "&amp;").replace("<", "&lt;")
    return (
        f'<div class="widget-unknown">'
        f'<div class="widget-label">{name}</div>'
        f'<pre>{safe_body}</pre></div>'
    )


def list_widgets() -> list[str]:
    """List all registered widget names."""
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Built-in widgets
# ---------------------------------------------------------------------------

@register("note")
def _widget_note(body: str, attrs: dict[str, str]) -> str:
    """Callout note — variants: info, warning, tip, danger."""
    variant = attrs.get("variant", "info")
    title = attrs.get("title", "")
    icons = {"info": "ℹ️", "warning": "⚠️", "tip": "💡", "danger": "🚨"}
    icon = icons.get(variant, "📝")
    colors = {
        "info": "var(--accent)",
        "warning": "var(--yellow)",
        "tip": "var(--green)",
        "danger": "var(--red)",
    }
    color = colors.get(variant, "var(--accent)")
    safe_body = body.replace("`", "\\`").replace("${", "\\${")
    title_html = f'<strong>{icon} {title}</strong>' if title else f'<span>{icon}</span>'
    return (
        f'<div class="w-note" style="border-left-color:{color};">'
        f'<div class="w-note-header">{title_html}</div>'
        f'<div class="prose" data-md="{_esc_attr(body)}"></div>'
        f'</div>'
    )


@register("mermaid")
def _widget_mermaid(body: str, attrs: dict[str, str]) -> str:
    """Mermaid diagram — rendered client-side."""
    title = attrs.get("title", "")
    caption = f'<div class="w-caption">{title}</div>' if title else ""
    return (
        f'<div class="w-mermaid">'
        f'<div class="mermaid">{body}</div>'
        f'{caption}</div>'
    )


@register("chart")
def _widget_chart(body: str, attrs: dict[str, str]) -> str:
    """Chart placeholder — renders a container for JS-driven visualization.

    attrs: type (line|bar|scatter|heatmap), src (data path), title, width, height
    """
    chart_type = attrs.get("type", "line")
    src = attrs.get("src", "")
    title = attrs.get("title", "")
    height = attrs.get("height", "300px")
    # The actual chart rendering happens client-side via a shared JS library
    return (
        f'<div class="w-chart" data-type="{chart_type}" data-src="{src}" '
        f'style="min-height:{height};">'
        f'{f"<div class=w-caption>{title}</div>" if title else ""}'
        f'<div class="w-chart-canvas"></div>'
        f'</div>'
    )


@register("artifact")
def _widget_artifact(body: str, attrs: dict[str, str]) -> str:
    """Artifact reference — embeds a mas-lab artifact viewer.

    attrs: type (kg|otel|trace|json|table|svg), src (file path)
    """
    art_type = attrs.get("type", "json")
    src = attrs.get("src", "")
    title = attrs.get("title", src)
    return (
        f'<div class="w-artifact" data-type="{art_type}" data-src="{src}">'
        f'<div class="w-artifact-header">{title}</div>'
        f'<div class="w-artifact-content">{body}</div>'
        f'</div>'
    )


@register("timeline")
def _widget_timeline(body: str, attrs: dict[str, str]) -> str:
    """Event timeline — vertical or horizontal."""
    orientation = attrs.get("orientation", "vertical")
    title = attrs.get("title", "")
    # Body contains timeline entries as markdown list items
    return (
        f'<div class="w-timeline" data-orientation="{orientation}">'
        f'{f"<div class=w-caption>{title}</div>" if title else ""}'
        f'<div class="prose" data-md="{_esc_attr(body)}"></div>'
        f'</div>'
    )


@register("code")
def _widget_code(body: str, attrs: dict[str, str]) -> str:
    """Code block with title and language."""
    lang = attrs.get("lang", attrs.get("language", ""))
    title = attrs.get("title", "")
    safe = body.replace("&", "&amp;").replace("<", "&lt;")
    title_html = f'<div class="w-code-title">{title}</div>' if title else ""
    return (
        f'<div class="w-code">'
        f'{title_html}'
        f'<pre><code class="language-{lang}">{safe}</code></pre>'
        f'</div>'
    )


@register("embed")
def _widget_embed(body: str, attrs: dict[str, str]) -> str:
    """HTML/iframe embed."""
    src = attrs.get("src", "")
    height = attrs.get("height", "500px")
    title = attrs.get("title", "")
    if src:
        return (
            f'<div class="w-embed">'
            f'{f"<div class=w-caption>{title}</div>" if title else ""}'
            f'<iframe src="{src}" style="width:100%;height:{height};border:none;border-radius:8px;"></iframe>'
            f'</div>'
        )
    # Inline HTML
    return f'<div class="w-embed">{body}</div>'


@register("figure")
def _widget_figure(body: str, attrs: dict[str, str]) -> str:
    """Figure with image and caption."""
    src = attrs.get("src", "")
    alt = attrs.get("alt", "")
    caption = attrs.get("caption", body.strip())
    width = attrs.get("width", "100%")
    return (
        f'<figure class="w-figure">'
        f'<img src="{src}" alt="{alt}" style="max-width:{width};border-radius:8px;">'
        f'<figcaption>{caption}</figcaption>'
        f'</figure>'
    )


@register("quote")
def _widget_quote(body: str, attrs: dict[str, str]) -> str:
    """Styled blockquote with attribution."""
    source = attrs.get("source", "")
    source_html = f'<cite>— {source}</cite>' if source else ""
    return (
        f'<blockquote class="w-quote">'
        f'<div class="prose" data-md="{_esc_attr(body)}"></div>'
        f'{source_html}'
        f'</blockquote>'
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc_attr(text: str) -> str:
    """Escape for HTML attribute."""
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
