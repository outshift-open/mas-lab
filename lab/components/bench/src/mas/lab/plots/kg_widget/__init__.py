#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""KG Widget — Python helpers.

Generates standalone HTML pages using the KGWidget JavaScript component.

Public API
----------
build_standalone_html(kg_data, title, opts)  ->  str
    Returns a complete self-contained HTML document embedding the widget.

serve_and_open(kg_data, title, opts, port)
    Starts a tiny HTTP server, opens the browser, waits for Ctrl-C.

get_widget_js()  ->  str
get_widget_css() ->  str
    Return the raw JS/CSS content for embedding in other HTML pages.
"""

import json
from pathlib import Path
from typing import Any


_HERE = Path(__file__).parent

# CDN URLs for Cytoscape and layout extensions
_CDN = [
    "https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js",
    "https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js",
    "https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.js",
    "https://cdn.jsdelivr.net/npm/layout-base@2.0.1/layout-base.js",
    "https://cdn.jsdelivr.net/npm/cose-base@2.2.0/cose-base.js",
    "https://cdn.jsdelivr.net/npm/cytoscape-cose-bilkent@4.1.0/cytoscape-cose-bilkent.js",
    "https://cdn.jsdelivr.net/npm/cytoscape-svg@0.4.0/cytoscape-svg.js",
]


def get_widget_js() -> str:
    """Return the KGWidget JavaScript source."""
    return (_HERE / "kg_widget.js").read_text(encoding="utf-8")


def get_widget_css() -> str:
    """Return the KGWidget CSS source."""
    return (_HERE / "kg_widget.css").read_text(encoding="utf-8")


def get_composer_js() -> str:
    """Return the KGComposer JavaScript source (composable views)."""
    return (_HERE / "kg_composer.js").read_text(encoding="utf-8")


def get_composer_css() -> str:
    """Return the KGComposer CSS source."""
    return (_HERE / "kg_composer.css").read_text(encoding="utf-8")


def build_standalone_html(
    kg_data: dict | str,
    title: str = "Knowledge Graph",
    opts: dict[str, Any] | None = None,
    *,
    offline: bool = False,
) -> str:
    """Build a complete standalone HTML page embedding the KGWidget.

    Parameters
    ----------
    kg_data:
        The KG JSON object ``{"nodes": [...], "edges": [...]}`` or its
        serialised form.
    title:
        Page / widget title displayed in the toolbar.
    opts:
        Widget options forwarded to ``new KGWidget(el, data, opts)`` (or
        ``new KGGraph(...)`` when ``component='graph'``).
        Keys: ``panelMode`` ('open'|'closed'), ``layout``, ``maxNodes``,
        ``title``, ``filterStyle`` ('flat'|'layered'),
        ``component`` ('widget'|'graph').
    offline:
        If True, inline all JS/CSS from disk (no CDN calls).  Useful when
        the page must work without internet access.
    """
    if isinstance(kg_data, str):
        kg_data = json.loads(kg_data)

    merged_opts: dict[str, Any] = {"panelMode": "open", "layout": "dagre", "title": title}
    if opts:
        merged_opts.update(opts)

    kg_json = json.dumps(kg_data, ensure_ascii=False)
    opts_json = json.dumps(merged_opts, ensure_ascii=False)

    if offline:
        cdn_tags = f"<style>{get_widget_css()}</style><script>{get_widget_js()}</script>"
        # Inline cytoscape too — requires local vendor files to be available
        # For now fall back to CDN even in offline mode for CDN scripts
        cdn_scripts = "\n".join(f'<script src="{u}"></script>' for u in _CDN)
    else:
        cdn_scripts = "\n".join(f'<script src="{u}"></script>' for u in _CDN)
        cdn_tags = (
            f'<style>{get_widget_css()}</style>'
            f'<script>{get_widget_js()}</script>'
        )

    node_count = len(kg_data.get("nodes", []))
    edge_count = len(kg_data.get("edges", []))
    subtitle = f"{node_count} nodes · {edge_count} edges"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0d1117; color: #e2e8f0; font-family: 'Inter', 'Segoe UI', sans-serif; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }}
    #kg-page-header {{ flex-shrink: 0; padding: 8px 14px; background: #161b22; border-bottom: 1px solid #21262d; display: flex; align-items: center; gap: 12px; }}
    #kg-page-header h1 {{ font-size: 14px; font-weight: 600; color: #e6edf3; }}
    #kg-page-header .sub {{ font-size: 11px; color: #6e7681; }}
    #kg-root {{ flex: 1; min-height: 0; }}
  </style>
  {cdn_scripts}
  {cdn_tags}
</head>
<body class="kg-widget-page">
  <div id="kg-page-header">
    <h1>{title}</h1>
    <span class="sub">{subtitle}</span>
  </div>
  <div id="kg-root"></div>
  <script>
    (function () {{
      var kg   = {kg_json};
      var opts = {opts_json};
      var root = document.getElementById('kg-root');
      // Give Cytoscape layout extensions time to register
      var Ctor = (opts.component === 'graph') ? window.KGGraph : window.KGWidget;
      window._kgWidget = new Ctor(root, kg, opts);
    }})();
  </script>
</body>
</html>"""


def serve_and_open(
    kg_data: dict | str,
    title: str = "Knowledge Graph",
    opts: dict[str, Any] | None = None,
    port: int = 0,
) -> None:
    """Generate the widget HTML and open it in the default browser.

    Opens a temporary in-process HTTP server on ``port`` (0 = random free
    port) and launches the system browser.  Blocks until Ctrl-C.
    """
    import socketserver
    import threading
    import webbrowser
    from http.server import SimpleHTTPRequestHandler
    import tempfile, os

    html = build_standalone_html(kg_data, title=title, opts=opts)

    # Write to a temp file so SimpleHTTPRequestHandler can serve static assets
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".html", mode="w", encoding="utf-8"
    ) as f:
        f.write(html)
        tmp_path = f.name

    class _Handler(SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path in ('/', '/index.html', f'/{os.path.basename(tmp_path)}'):
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):  # silence access log
            pass

    with socketserver.TCPServer(("127.0.0.1", port), _Handler) as httpd:
        actual_port = httpd.server_address[1]
        url = f"http://127.0.0.1:{actual_port}/"
        print(f"  KG viewer → {url}  (Ctrl-C to stop)")
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.debug('suppressed', exc_info=True)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug('suppressed', exc_info=True)
