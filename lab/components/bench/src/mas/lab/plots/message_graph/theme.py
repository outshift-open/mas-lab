#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Theme/CSS for message-graph SVG and HTML."""

# ---------------------------------------------------------------------------
# Theme system — CSS custom properties
# ---------------------------------------------------------------------------

# Light theme token values
_LIGHT: dict[str, str] = {
    "mg-bg":         "#ffffff",
    "mg-band":       "#f0f4ff",
    "mg-band-alt":   "#e8ecfa",
    "mg-band-lbl":   "#888",
    "mg-lane":       "#ccc",
    "mg-lane-lbl":   "#444",
    "mg-edge":       "#888",
    "mg-arrow":      "#888",
    "mg-tool-sq":    "#ccc",
    "mg-tool-tick":  "#aaa",
    "mg-title":      "#333",
    "mg-legend-sep": "#e0e4ef",
    "mg-legend-lbl": "#555",
}

# Dark theme token values  (Catppuccin Mocha palette)
_DARK: dict[str, str] = {
    "mg-bg":         "#181825",
    "mg-band":       "#1e1e2e",
    "mg-band-alt":   "#24273a",
    "mg-band-lbl":   "#6c7086",
    "mg-lane":       "#313244",
    "mg-lane-lbl":   "#cdd6f4",
    "mg-edge":       "#585b70",
    "mg-arrow":      "#585b70",
    "mg-tool-sq":    "#45475a",
    "mg-tool-tick":  "#45475a",
    "mg-title":      "#cdd6f4",
    "mg-legend-sep": "#313244",
    "mg-legend-lbl": "#a6adc8",
}


def _vars_block(tokens: dict[str, str], indent: str = "  ") -> str:
    """Render a theme dict as CSS custom property declarations."""
    return "".join(f"{indent}--{k}: {v};\n" for k, v in tokens.items())


# Static CSS class rules — all colours via var()
_SVG_CLASS_STYLES = """\
  .mg-bg           { fill: var(--mg-bg); }
  .iteration-band  { fill: var(--mg-band); }
  .iteration-band--alt { fill: var(--mg-band-alt); }
  .iteration-label { font: bold 10px sans-serif; text-anchor: middle;
                     fill: var(--mg-band-lbl); }
  .lane-line       { stroke: var(--mg-lane); stroke-width: 1; fill: none; }
  .lane-label      { font: 12px sans-serif; text-anchor: end;
                     dominant-baseline: middle; fill: var(--mg-lane-lbl); }
  .graph-edge      { fill: none; stroke: var(--mg-edge); stroke-width: 1.5; }
  .mg-arrow-path   { fill: var(--mg-arrow); }
  .turn-rect       { }
  .turn-label      { font: bold 10px sans-serif; text-anchor: middle;
                     dominant-baseline: middle; fill: white; }
  .tool-tick       { stroke: var(--mg-tool-tick); stroke-width: 1; }
  .tool-square     { fill: var(--mg-tool-sq); }
  .graph-title     { font: bold 13px sans-serif; text-anchor: middle;
                     fill: var(--mg-title); }
  .legend-sep      { stroke: var(--mg-legend-sep); stroke-width: 1; }
  .legend-label    { font: 11px sans-serif; dominant-baseline: middle;
                     fill: var(--mg-legend-lbl); }
  .time-axis-line  { stroke: var(--mg-lane); stroke-width: 1; fill: none; }
  .time-tick       { stroke: var(--mg-lane); stroke-width: 1; }
  .time-label      { font: 9px sans-serif; text-anchor: middle;
                     fill: var(--mg-band-lbl); }
"""


def _build_svg_css(theme: str, standalone: bool = True) -> str:
    """Return the full CSS to embed in the SVG ``<style>`` block.

    ``standalone=True`` (SVG file): embed theme variables directly, including
    a ``@media (prefers-color-scheme: dark)`` rule when *theme* is ``"auto"``.

    ``standalone=False`` (SVG inside HTML): only emit light defaults — the HTML
    wrapper injects dark overrides via ``html[data-theme="dark"]``.
    """
    light = _vars_block(_LIGHT)
    dark  = _vars_block(_DARK)

    if not standalone:
        # HTML wrapper handles dark mode; just supply light defaults
        var_css = f":root {{\n{light}}}\n"
    elif theme == "dark":
        var_css = f":root {{\n{dark}}}\n"
    elif theme == "light":
        var_css = f":root {{\n{light}}}\n"
    else:  # "auto"
        var_css = (
            f":root {{\n{light}}}\n"
            f"@media (prefers-color-scheme: dark) {{\n"
            f"  :root {{\n{_vars_block(_DARK, '    ')}  }}\n"
            f"}}\n"
        )
    return var_css + _SVG_CLASS_STYLES

_HTML_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>{title}</title>
<script>
/* Anti-FOUC: apply theme before first paint */
(function() {{
  var t = localStorage.getItem('mg-theme') || '{initial_theme}';
  var eff = t === 'auto'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : t;
  document.documentElement.setAttribute('data-theme', eff);
}})();
</script>
<style>
  /* ── Chrome custom properties ── */
  :root {{
    --ch-bg: #f3f4f6; --ch-header: #ffffff; --ch-border: #e5e7eb;
    --ch-text: #111827; --ch-ctrl: #e5e7eb; --ch-ctrl-hover: #d1d5db;
    --ch-shadow: rgba(0,0,0,.12);
  }}
  /* ── Dark overrides — chrome + SVG tokens ── */
  html[data-theme="dark"] {{
    --ch-bg: #1e1e2e; --ch-header: #181825; --ch-border: #313244;
    --ch-text: #cdd6f4; --ch-ctrl: #313244; --ch-ctrl-hover: #45475a;
    --ch-shadow: rgba(0,0,0,.4);
    --mg-bg: #181825; --mg-band: #1e1e2e; --mg-band-alt: #24273a;
    --mg-band-lbl: #6c7086; --mg-lane: #313244; --mg-lane-lbl: #cdd6f4;
    --mg-edge: #585b70; --mg-arrow: #585b70;
    --mg-tool-sq: #45475a; --mg-tool-tick: #45475a;
    --mg-title: #cdd6f4; --mg-legend-sep: #313244; --mg-legend-lbl: #a6adc8;
  }}
  /* ── Layout ── */
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ background: var(--ch-bg); color: var(--ch-text);
          font-family: system-ui, sans-serif; margin: 0;
          transition: background .2s, color .2s; }}
  header {{ padding: 8px 12px; background: var(--ch-header);
            border-bottom: 1px solid var(--ch-border);
            display: flex; align-items: center; gap: 8px; }}
  header h1 {{ font-size: 14px; margin: 0; flex: 1; color: var(--ch-text); }}
  .ctrl {{ background: var(--ch-ctrl); border: 1px solid var(--ch-border);
           color: var(--ch-text); padding: 4px 10px; border-radius: 4px;
           cursor: pointer; font-size: 13px; transition: background .15s; }}
  .ctrl:hover {{ background: var(--ch-ctrl-hover); }}
  #container {{ overflow: auto; padding: 20px; }}
  #container svg {{ border-radius: 6px; box-shadow: 0 2px 12px var(--ch-shadow); }}
  .legend {{ display: flex; gap: 18px; font-size: 11px; padding: 6px 12px;
             background: var(--ch-header); border-top: 1px solid var(--ch-border);
             flex-wrap: wrap; color: var(--ch-text); }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-swatch {{ width: 14px; height: 14px; border-radius: 2px; flex-shrink: 0; }}
  /* ── Tooltip panel ── */
  #mg-tip {{
    position: fixed; display: none; pointer-events: none; z-index: 9999;
    background: var(--ch-header); color: var(--ch-text);
    border: 1px solid var(--ch-border); border-radius: 6px;
    box-shadow: 0 4px 16px var(--ch-shadow);
    max-width: 440px; max-height: 380px; overflow-y: auto;
  }}
  #mg-tip-hd {{
    font-weight: 700; font-size: 12px; padding: 6px 10px 5px;
    border-bottom: 1px solid var(--ch-border);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  #mg-tip-bd {{
    padding: 6px 10px; white-space: pre-wrap;
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 11px; opacity: 0.9; line-height: 1.5;
  }}
  [data-tip-label] {{ cursor: pointer; }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <button class="ctrl" id="theme-toggle" onclick="cycleTheme()" title="Toggle theme">⚙ Auto</button>
  <button class="ctrl" onclick="zoom(1.25)">&#43;</button>
  <button class="ctrl" onclick="zoom(0.8)">&minus;</button>
  <button class="ctrl" onclick="resetZoom()">Reset</button>
  <button class="ctrl" onclick="downloadSvg()">&#8595; SVG</button>
</header>
<div id="container">{svg}</div>
<div class="legend" id="legend"></div>
<div id="mg-tip"><div id="mg-tip-hd"></div><div id="mg-tip-bd"></div></div>
<script>
const THEMES = ['auto', 'light', 'dark'];
const ICONS  = {{'auto': '⚙ Auto', 'light': '☀ Light', 'dark': '☾ Dark'}};
const KEY    = 'mg-theme';
let scale    = 1;
const svgEl  = document.querySelector('#container svg');

function getStored() {{ return localStorage.getItem(KEY) || '{initial_theme}'; }}

function applyTheme(t) {{
  const eff = t === 'auto'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : t;
  document.documentElement.setAttribute('data-theme', eff);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = ICONS[t] || t;
}}

function cycleTheme() {{
  const next = THEMES[(THEMES.indexOf(getStored()) + 1) % THEMES.length];
  localStorage.setItem(KEY, next);
  applyTheme(next);
}}

applyTheme(getStored());
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {{
  if (getStored() === 'auto') applyTheme('auto');
}});

function zoom(f) {{
  scale *= f;
  svgEl.style.transform = 'scale(' + scale + ')';
  svgEl.style.transformOrigin = 'top left';
}}
function resetZoom() {{ scale = 1; svgEl.style.transform = ''; }}
function downloadSvg() {{
  const blob = new Blob([svgEl.outerHTML], {{type: 'image/svg+xml'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'message-graph.svg'; a.click();
}}

const swatches = {{}};
svgEl.querySelectorAll('[data-agent]').forEach(el => {{
  const agent = el.getAttribute('data-agent');
  const color = el.getAttribute('data-color');
  if (agent && color) swatches[agent] = color;
}});
const legend = document.getElementById('legend');
Object.entries(swatches).forEach(([agent, color]) => {{
  const item = document.createElement('div'); item.className = 'legend-item';
  item.innerHTML = '<div class="legend-swatch" style="background:' + color + '"></div>' + agent;
  legend.appendChild(item);
}});

// ── Tooltips ───────────────────────────────────────────────────────
const _tip = document.getElementById('mg-tip');
const _tipHd = document.getElementById('mg-tip-hd');
const _tipBd = document.getElementById('mg-tip-bd');

function _posTip(e) {{
  const m = 16, tw = _tip.offsetWidth || 440, th = _tip.offsetHeight || 200;
  let l = e.clientX + m, t = e.clientY - 30;
  if (l + tw > window.innerWidth)  l = e.clientX - tw - m;
  if (t + th > window.innerHeight) t = window.innerHeight - th - 4;
  _tip.style.left = Math.max(4, l) + 'px';
  _tip.style.top  = Math.max(4, t) + 'px';
}}

svgEl.addEventListener('mousemove', function(e) {{
  let el = e.target;
  while (el && el !== svgEl) {{
    if (el.dataset && el.dataset.tipLabel) {{
      _tipHd.textContent = el.dataset.tipLabel;
      _tipBd.textContent = el.dataset.tipBody || '';
      _tip.style.display = 'block';
      _posTip(e);
      return;
    }}
    el = el.parentElement;
  }}
  _tip.style.display = 'none';
}});

svgEl.addEventListener('mouseleave', () => {{ _tip.style.display = 'none'; }});
</script>
</body>
</html>"""
