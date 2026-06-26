//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
/**
 * KGComposer — Composable MAS Knowledge-Graph visualiser
 *
 * Provides composable, plugin-like views:
 *   KGFilterMatrix   — matrix filter panel (LAYERS × nodes/innerEdges/outerEdges/group)
 *   KGLatentView     — latent space scatter plot (2D projection of KG nodes)
 *   KGAggregateView  — node/edge count statistics
 *   KGComposer       — main compositor wiring all views together
 *
 * Requires kg_widget.js (KGGraph / KGWidget) to be loaded first.
 *
 * Usage:
 *   const c = new KGComposer(el, kgData, {
 *     kg_view:        true,
 *     latent_view:    false,
 *     aggregate_view: false,
 *     filter_panel:   'matrix',   // 'matrix' | 'layered' | 'flat' | false
 *     filter_schema:  true,
 *     panel_mode:     'open',
 *     theme:          'dark',
 *     preset:         'agents-calls',
 *   });
 *
 *   c.setData(newKg);
 *   c.applyPreset('governance');
 *   c.setTheme('light');
 *   c.destroy();
 */
(function (global) {
  'use strict';

  // ─── Ontology blocks (static, from old/viz data.py) ─────────────────────
  const BLOCKS = [
    { id: 'execution',  label: 'Execution',     color: '#9B59B6', icon: '⚙' },
    { id: 'trajectory', label: 'Trajectory',    color: '#16A085', icon: '→' },
    { id: 'metrics',    label: 'Metrics',       color: '#E74C3C', icon: '≡' },
    { id: 'otel',       label: 'OpenTelemetry', color: '#95A5A6', icon: '◌' },
  ];

  // ─── Semantic layers (from old/viz ontology.layers) ───────────────────────
  const LAYERS = [
    { id: 'raw',        label: 'Raw',        color: '#2C3E50', icon: '◌', types: ['CallAnnotation'] },
    { id: 'normalized', label: 'Normalized', color: '#34495E', icon: '◎', types: ['Session','Run'] },
    { id: 'syntactic',  label: 'Syntactic',  color: '#5DADE2', icon: '≈', types: ['LLMCall','ToolCall','ProcessingCall'] },
    { id: 'semantic',   label: 'Semantic',   color: '#3498DB', icon: '◈', types: ['Agent','Worker','MASCall','AgentCall','RAGQuery'] },
    { id: 'symbolic',   label: 'Symbolic',   color: '#2ECC71', icon: '⌖', types: ['Tool','LLM','Skill','State','Transition'] },
    { id: 'causal',     label: 'Causal',     color: '#E67E22', icon: '⇢', types: ['NetworkCall','TaskCall','MemoryCall','ParallelGroup','Branch'] },
    { id: 'governance', label: 'Governance', color: '#E74C3C', icon: '⚖', types: ['GovernanceEvent','PolicyDenial','PolicyAllow','HITLGate','BudgetEvent','ControlIntervention','TransformationEvent'] },
  ];

  const TYPE_TO_LAYER = {};
  LAYERS.forEach(function (l) { l.types.forEach(function (t) { TYPE_TO_LAYER[t] = l.id; }); });

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ─── Composer presets ──────────────────────────────────────────────────────
  // layers: null → show all; otherwise per-layer overrides (unspecified layers → off).
  // Each layer entry defaults to { nodes:true, innerEdges:true, outerEdges:true, group:false }.
  const COMPOSER_PRESETS = [
    {
      id: 'all', label: 'All', desc: 'Show all layers and types',
      layers: null,
    },
    {
      id: 'agents-calls', label: 'Agents + Calls', desc: 'Agent execution flow',
      layers: {
        normalized: { nodes: true, innerEdges: false, outerEdges: false, group: false },
        semantic:   {},
        syntactic:  {},
      },
    },
    {
      id: 'llm-trace', label: 'LLM Trace', desc: 'Agents, LLM calls and states',
      layers: {
        semantic: {},
        syntactic: {},
        symbolic: { nodes: true, innerEdges: false, outerEdges: true, group: false },
      },
    },
    {
      id: 'memory-flow', label: 'Memory Flow', desc: 'States and transitions',
      layers: {
        semantic: { nodes: true, innerEdges: false, outerEdges: true, group: false },
        symbolic: {},
      },
    },
    {
      id: 'resources', label: 'Resources', desc: 'Tools, LLMs, Skills and their calls',
      layers: {
        symbolic:  {},
        syntactic: {},
      },
    },
    {
      id: 'governance', label: 'Governance', desc: 'Governance events and policy decisions',
      layers: {
        governance: {},
        syntactic: { nodes: true, innerEdges: false, outerEdges: true, group: false },
      },
    },
    {
      id: 'top-level', label: 'Top Level', desc: 'Session, Run and Agents only',
      layers: {
        normalized: {},
        semantic:   {},
      },
    },
  ];

  // ─── Span levels (exact match with old/viz app.js spanTypes) ─────────────
  const SPANS = [
    { id: 'mas',      label: 'MAS',       color: '#9B59B6' },
    { id: 'agent',    label: 'Agent',     color: '#3498DB' },
    { id: 'task',     label: 'Task',      color: '#2ECC71' },
    { id: 'toolcall', label: 'Tool Call', color: '#E67E22' },
    { id: 'llm_call', label: 'LLM Call',  color: '#E74C3C' },
  ];

  // Build full 3-section filter state — all sections are static constants
  function makeFullState() {
    var state = { layers: {}, blocks: {}, spans: {} };
    LAYERS.forEach(function (l) {
      state.layers[l.id] = { nodes: true, innerEdges: true, outerEdges: true, group: false };
    });
    BLOCKS.forEach(function (b) {
      state.blocks[b.id] = { nodes: true, innerEdges: true, outerEdges: true, group: true };
    });
    SPANS.forEach(function (s) {
      state.spans[s.id] = { nodes: true, innerEdges: true, outerEdges: true, group: false };
    });
    return state;
  }

  // Apply preset — works on state.layers (backward compat: also accepts flat state)
  function applyPresetToState(state, presetId) {
    var preset = COMPOSER_PRESETS.find(function (p) { return p.id === presetId; });
    if (!preset) return;
    var layers = state.layers || state;  // backward compat
    if (preset.layers === null) {
      LAYERS.forEach(function (l) {
        layers[l.id] = { nodes: true, innerEdges: true, outerEdges: true, group: false };
      });
      return;
    }
    LAYERS.forEach(function (l) {
      layers[l.id] = { nodes: false, innerEdges: false, outerEdges: false, group: false };
    });
    Object.keys(preset.layers).forEach(function (layerId) {
      layers[layerId] = Object.assign(
        { nodes: true, innerEdges: true, outerEdges: true, group: false },
        preset.layers[layerId]
      );
    });
  }

  // ════════════════════════════════════════════════════════════════════════════
  // KGFilterMatrix — old/viz-style matrix filter panel
  //
  //   BLOCKS      × [● ⟷ ⇄ ▢ ◉]   — execution / trajectory / metrics / otel
  //   LAYERS      × [● ⟷ ⇄ ▢ ◉]   — 7 semantic layers (old/viz ontology)
  //   SPAN LEVELS × [● ⟷ ⇄ ▢ ◉]   — MAS / Agent / Task / Tool Call / LLM Call
  //
  // State: { layers:{[id]:{nodes,innerEdges,outerEdges,group}},
  //          blocks:{[id]:{...}}, spans:{[id]:{...}} }
  // ════════════════════════════════════════════════════════════════════════════
  function KGFilterMatrix(containerEl, kg, opts) {
    opts = Object.assign({ theme: 'dark', preset: null, onChange: null }, opts || {});
    this._container = containerEl;
    this._kg        = kg || { nodes: [], edges: [] };
    this._opts      = opts;
    this._theme     = opts.theme;
    this._onChange  = opts.onChange;
    this._state     = makeFullState();
    if (opts.preset) applyPresetToState(this._state, opts.preset);
    this._buildDOM();
    this._bindEvents();
  }

  KGFilterMatrix._COLS = [
    { key: 'nodes',      sym: '●', tip: 'Nodes' },
    { key: 'innerEdges', sym: '⟷', tip: 'Inner edges' },
    { key: 'outerEdges', sym: '⇄', tip: 'Outer edges' },
    { key: 'group',      sym: '▢', tip: 'Group nodes' },
    { key: 'all',        sym: '◉', tip: 'Toggle all' },
  ];

  // Build HTML for one section (header + rows)
  KGFilterMatrix.prototype._buildSection = function (sectionKey, sectionTitle, items) {
    var cols  = KGFilterMatrix._COLS;
    var state = this._state[sectionKey] || {};

    var hdrCols = cols.map(function (c) {
      return '<div class="kgc-fm-toggle kgc-fm-hdr-toggle" data-col="' + c.key
        + '" data-section="' + sectionKey + '" title="' + c.tip + '">' + c.sym + '</div>';
    }).join('');

    var html =
      '<div class="kgc-fm-section" data-section="' + sectionKey + '">'
      + '<div class="kgc-fm-section-hdr" data-section="' + sectionKey + '">'
      + '<div class="kgc-fm-section-title">' + sectionTitle + '</div>'
      + '<div class="kgc-fm-section-cols">' + hdrCols + '</div>'
      + '</div>';

    if (!items.length) {
      html += '<div class="kgc-fm-empty">—</div>';
    } else {
      items.forEach(function (item) {
        var st = state[item.id] || { nodes: true, innerEdges: true, outerEdges: true, group: false };
        var rowCols = cols.map(function (c) {
          var cls;
          if (c.key === 'all') {
            var allOn = st.nodes && st.innerEdges && st.outerEdges && st.group;
            var anyOn = st.nodes || st.innerEdges || st.outerEdges || st.group;
            cls = allOn ? 'active' : (anyOn ? 'partial' : 'inactive');
          } else {
            cls = st[c.key] ? 'active' : 'inactive';
          }
          return '<div class="kgc-fm-toggle ' + cls + '" data-col="' + c.key
            + '" data-section="' + sectionKey + '" data-item="' + esc(item.id)
            + '" title="' + c.tip + '">' + c.sym + '</div>';
        }).join('');
        html +=
          '<div class="kgc-fm-row" data-section="' + sectionKey + '" data-item="' + esc(item.id) + '">'
          + '<div class="kgc-fm-row-left">'
          + '<span class="kgc-fm-color-tag" style="background:' + item.color + '"></span>'
          + (item.icon ? '<span class="kgc-fm-row-icon">' + item.icon + '</span>' : '')
          + '<span class="kgc-fm-row-name">' + esc(item.label) + '</span>'
          + (item.count != null ? '<span class="kgc-fm-count' + (item.count ? '' : ' kgc-fm-count--zero') + '">' + item.count + '</span>' : '')
          + '</div>'
          + '<div class="kgc-fm-row-right">' + rowCols + '</div>'
          + '</div>';
      });
    }
    html += '</div>';
    return html;
  };

  KGFilterMatrix.prototype._buildDOM = function () {
    var kg    = this._kg;
    var isDark = this._theme !== 'light';
    this._container.className = 'kgc-filter-matrix ' + (isDark ? 'kgc-dark' : 'kgc-light');

    // Node counts per layer
    var typeCounts = {};
    (kg.nodes || []).forEach(function (n) { typeCounts[n.node_type] = (typeCounts[n.node_type] || 0) + 1; });
    var layerItems = LAYERS.map(function (l) {
      var count = l.types.reduce(function (s, t) { return s + (typeCounts[t] || 0); }, 0);
      return { id: l.id, label: l.label, icon: l.icon, color: l.color, count: count };
    });
    var spanItems = SPANS.map(function (s) { return { id: s.id, label: s.label, color: s.color }; });

    var html = '';
    html += this._buildSection('blocks', 'BLOCKS',      BLOCKS);
    html += this._buildSection('layers', 'LAYERS',      layerItems);
    html += this._buildSection('spans',  'SPAN LEVELS', spanItems);
    html +=
      '<div class="kgc-fm-presets">'
      + '<div class="kgc-fm-presets-title">PRESETS</div>'
      + COMPOSER_PRESETS.map(function (p) {
          return '<button class="kgc-fm-preset-btn" data-preset="' + p.id
            + '" title="' + esc(p.desc) + '">' + esc(p.label) + '</button>';
        }).join('')
      + '</div>';

    this._container.innerHTML = html;
    this._syncAllHdrs();
  };

  // Sync a data row's toggle classes from state
  KGFilterMatrix.prototype._syncRow = function (sectionKey, itemId) {
    var row = this._container.querySelector(
      '.kgc-fm-row[data-section="' + sectionKey + '"][data-item="' + itemId + '"]'
    );
    if (!row) return;
    var st = (this._state[sectionKey] || {})[itemId];
    if (!st) return;
    row.querySelectorAll('.kgc-fm-toggle').forEach(function (btn) {
      var col = btn.dataset.col;
      if (col === 'all') {
        var allOn = st.nodes && st.innerEdges && st.outerEdges && st.group;
        var anyOn = st.nodes || st.innerEdges || st.outerEdges || st.group;
        btn.className = 'kgc-fm-toggle ' + (allOn ? 'active' : anyOn ? 'partial' : 'inactive');
      } else {
        btn.className = 'kgc-fm-toggle ' + (st[col] ? 'active' : 'inactive');
      }
    });
  };

  // Sync a section header's aggregate state
  KGFilterMatrix.prototype._syncSectionHdr = function (sectionKey) {
    var hdr = this._container.querySelector('.kgc-fm-section-hdr[data-section="' + sectionKey + '"]');
    if (!hdr) return;
    var items = Object.values(this._state[sectionKey] || {});
    if (!items.length) return;
    hdr.querySelectorAll('.kgc-fm-hdr-toggle').forEach(function (btn) {
      var col = btn.dataset.col;
      if (col === 'all') {
        var allOn = items.every(function (st) { return st.nodes && st.innerEdges && st.outerEdges && st.group; });
        var anyOn = items.some(function (st)  { return st.nodes || st.innerEdges || st.outerEdges || st.group; });
        btn.className = 'kgc-fm-toggle kgc-fm-hdr-toggle ' + (allOn ? 'active' : anyOn ? 'partial' : 'inactive');
      } else {
        var allOn2 = items.every(function (st) { return !!st[col]; });
        var anyOn2 = items.some(function (st)  { return !!st[col]; });
        btn.className = 'kgc-fm-toggle kgc-fm-hdr-toggle ' + (allOn2 ? 'active' : anyOn2 ? 'partial' : 'inactive');
      }
    });
  };

  KGFilterMatrix.prototype._syncAllHdrs = function () {
    this._syncSectionHdr('blocks');
    this._syncSectionHdr('layers');
    this._syncSectionHdr('spans');
  };

  KGFilterMatrix.prototype._bindEvents = function () {
    var self = this;
    this._container.addEventListener('click', function (evt) {

      // ── Section header column toggle ─────────────────────────────────
      var hdrToggle = evt.target.closest('.kgc-fm-hdr-toggle');
      if (hdrToggle) {
        var section = hdrToggle.dataset.section;
        var col     = hdrToggle.dataset.col;
        var sectionState = self._state[section] || {};
        var ids = Object.keys(sectionState);
        if (col === 'all') {
          var allOn = ids.every(function (id) {
            var s = sectionState[id]; return s.nodes && s.innerEdges && s.outerEdges && s.group;
          });
          ids.forEach(function (id) {
            sectionState[id].nodes = sectionState[id].innerEdges =
            sectionState[id].outerEdges = sectionState[id].group = !allOn;
          });
        } else {
          var colAllOn = ids.every(function (id) { return !!sectionState[id][col]; });
          ids.forEach(function (id) { sectionState[id][col] = !colAllOn; });
        }
        ids.forEach(function (id) { self._syncRow(section, id); });
        self._syncSectionHdr(section);
        if (self._onChange) self._onChange(self._state);
        return;
      }

      // ── Per-row item toggle ──────────────────────────────────────────
      var rowToggle = evt.target.closest('.kgc-fm-toggle:not(.kgc-fm-hdr-toggle)');
      if (rowToggle) {
        var row = rowToggle.closest('.kgc-fm-row');
        if (!row) return;
        var rowSection = row.dataset.section;
        var itemId     = row.dataset.item;
        var rowCol     = rowToggle.dataset.col;
        var rowState   = (self._state[rowSection] || {})[itemId];
        if (!rowState) return;
        if (rowCol === 'all') {
          var rowAllOn = rowState.nodes && rowState.innerEdges && rowState.outerEdges && rowState.group;
          rowState.nodes = rowState.innerEdges = rowState.outerEdges = rowState.group = !rowAllOn;
        } else {
          rowState[rowCol] = !rowState[rowCol];
        }
        self._syncRow(rowSection, itemId);
        self._syncSectionHdr(rowSection);
        if (self._onChange) self._onChange(self._state);
        return;
      }

      // ── Preset button ────────────────────────────────────────────────
      var presetBtn = evt.target.closest('.kgc-fm-preset-btn');
      if (presetBtn) {
        applyPresetToState(self._state, presetBtn.dataset.preset);
        // Reset blocks and spans to all-on
        Object.keys(self._state.blocks).forEach(function (id) {
          self._state.blocks[id] = { nodes: true, innerEdges: true, outerEdges: true, group: true };
        });
        Object.keys(self._state.spans).forEach(function (id) {
          self._state.spans[id] = { nodes: true, innerEdges: true, outerEdges: true, group: false };
        });
        self._buildDOM();
        self._bindEvents();
        if (self._onChange) self._onChange(self._state);
      }
    });
  };

  // ── KGFilterMatrix public API ──────────────────────────────────────────────
  KGFilterMatrix.prototype.getState = function () { return this._state; };

  KGFilterMatrix.prototype.applyPreset = function (presetId) {
    applyPresetToState(this._state, presetId);
    this._buildDOM();
    this._bindEvents();
    if (this._onChange) this._onChange(this._state);
  };

  KGFilterMatrix.prototype.setData = function (kg) {
    this._kg = kg || { nodes: [], edges: [] };
    // Rebuild DOM to refresh node counts per layer
    this._buildDOM();
    this._bindEvents();
  };

  KGFilterMatrix.prototype.setTheme = function (theme) {
    this._theme = theme;
    this._container.className = 'kgc-filter-matrix ' + (theme !== 'light' ? 'kgc-dark' : 'kgc-light');
  };

  // ════════════════════════════════════════════════════════════════════════════
  // KGLatentView — latent space scatter plot
  //
  // Computes 2D positions from:
  //   1. Node properties x, y (explicit coords)
  //   2. Node property embedding[0..1] (first two embedding dims)
  //   3. Fallback: radial layer layout (each layer as an angular cluster)
  //
  // Usage (standalone):
  //   const v = new KGLatentView(el, kg, { theme:'dark', onNodeClick: fn });
  //   v.setFilter(nodeTypeSet);
  //   v.highlightNode(nodeId);
  // ════════════════════════════════════════════════════════════════════════════
  function KGLatentView(containerEl, kg, opts) {
    opts = Object.assign({ theme: 'dark', onNodeClick: null }, opts || {});
    this._container      = containerEl;
    this._kg             = kg || { nodes: [], edges: [] };
    this._opts           = opts;
    this._theme          = opts.theme;
    this._onNodeClick    = opts.onNodeClick;
    this._activeNodeTypes = null;
    this._buildDOM();
    this._render();
  }

  KGLatentView.prototype._computePositions = function (nodes) {
    if (!nodes.length) return [];

    // 1. Explicit x, y coords
    if (nodes[0].x != null && nodes[0].y != null) {
      return nodes.map(n => ({ id: n.id, x: +n.x, y: +n.y, node: n }));
    }

    // 2. Embedding: use first two dimensions
    if (Array.isArray(nodes[0].embedding) && nodes[0].embedding.length >= 2) {
      return nodes.map(n => ({
        id: n.id, x: n.embedding[0], y: n.embedding[1], node: n,
      }));
    }

    // 3. Radial layout by layer
    const layerNodes = {};
    LAYERS.forEach(l => { layerNodes[l.id] = []; });
    nodes.forEach(n => {
      const lid = TYPE_TO_LAYER[n.node_type] || 'normalized';
      (layerNodes[lid] || (layerNodes[lid] = [])).push(n);
    });

    const numLayers = LAYERS.length;
    const positions = [];
    LAYERS.forEach((l, li) => {
      const lNodes = layerNodes[l.id] || [];
      if (!lNodes.length) return;
      const angle  = (li / numLayers) * 2 * Math.PI - Math.PI / 2;
      const radius = 0.52;
      const cx = Math.cos(angle) * radius;
      const cy = Math.sin(angle) * radius;
      const clusterR = Math.min(0.14, 0.06 + lNodes.length * 0.008);
      lNodes.forEach((n, ni) => {
        const a = (ni / Math.max(lNodes.length, 1)) * 2 * Math.PI;
        positions.push({
          id:   n.id,
          x:    cx + (lNodes.length > 1 ? Math.cos(a) * clusterR : 0),
          y:    cy + (lNodes.length > 1 ? Math.sin(a) * clusterR : 0),
          node: n,
        });
      });
    });
    return positions;
  };

  KGLatentView.prototype._buildDOM = function () {
    this._container.className = 'kgc-latent ' + (this._theme !== 'light' ? 'kgc-dark' : 'kgc-light');
    this._container.innerHTML =
      '<div class="kgc-latent-header">'
      + '<span class="kgc-latent-title">Latent Space</span>'
      + '<span class="kgc-latent-hint">Node clusters by semantic layer</span>'
      + '</div>'
      + '<div class="kgc-latent-canvas-wrap">'
      + '<svg class="kgc-latent-svg" xmlns="http://www.w3.org/2000/svg"></svg>'
      + '</div>'
      + '<div class="kgc-latent-legend"></div>';
    this._svgEl    = this._container.querySelector('.kgc-latent-svg');
    this._legendEl = this._container.querySelector('.kgc-latent-legend');
  };

  KGLatentView.prototype._render = function () {
    const allNodes = this._kg.nodes || [];
    const nodes    = allNodes.filter(n => {
      if (!this._activeNodeTypes) return true;
      return this._activeNodeTypes.has(n.node_type);
    });

    const isDark    = this._theme !== 'light';
    const bgColor   = isDark ? '#0d1117' : '#f8fafc';
    const noDataClr = isDark ? '#475569' : '#94a3b8';

    if (!nodes.length) {
      this._svgEl.setAttribute('viewBox', '0 0 400 260');
      this._svgEl.style.background = bgColor;
      this._svgEl.innerHTML =
        '<text x="200" y="130" text-anchor="middle" fill="' + noDataClr + '" font-size="12">No nodes to display</text>';
      this._legendEl.innerHTML = '';
      return;
    }

    const positions = this._computePositions(nodes);

    // Normalize to [margin, W-margin] × [margin, H-margin]
    const W = 400, H = 300, margin = 18;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    positions.forEach(p => {
      if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
    });
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;

    const nx = p => margin + ((p.x - minX) / rangeX) * (W - 2 * margin);
    const ny = p => margin + ((p.y - minY) / rangeY) * (H - 2 * margin);

    const layerColor = {};
    LAYERS.forEach(l => { layerColor[l.id] = l.color; });

    let dotsSVG = '';
    positions.forEach(p => {
      const lid   = TYPE_TO_LAYER[p.node.node_type] || null;
      const color = lid ? layerColor[lid] : noDataClr;
      const cx    = nx(p).toFixed(1);
      const cy    = ny(p).toFixed(1);
      dotsSVG +=
        '<circle cx="' + cx + '" cy="' + cy + '" r="4"'
        + ' fill="' + color + '" fill-opacity="0.85"'
        + ' stroke="' + (isDark ? '#0d1117' : '#fff') + '" stroke-width="0.8"'
        + ' data-id="' + esc(p.id) + '" data-layer="' + (lid || '') + '"'
        + ' class="kgc-latent-dot"><title>' + esc((p.node.node_type || '') + ': ' + (p.id || '')) + '</title></circle>';
    });

    this._svgEl.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    this._svgEl.setAttribute('width',  '100%');
    this._svgEl.setAttribute('height', '100%');
    this._svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    this._svgEl.style.background = bgColor;
    this._svgEl.innerHTML = dotsSVG;

    // Legend
    const presentLayers = new Set(positions.map(p => TYPE_TO_LAYER[p.node.node_type]).filter(Boolean));
    this._legendEl.innerHTML = LAYERS.filter(l => presentLayers.has(l.id)).map(l =>
      '<span class="kgc-latent-legend-item">'
      + '<span class="kgc-latent-legend-dot" style="background:' + l.color + '"></span>'
      + esc(l.label) + '</span>'
    ).join('');

    // Click handlers
    const self = this;
    this._svgEl.querySelectorAll('.kgc-latent-dot').forEach(dot => {
      dot.addEventListener('click', function () {
        self._svgEl.querySelectorAll('.kgc-latent-dot').forEach(d => d.classList.remove('kgc-selected'));
        this.classList.add('kgc-selected');
        if (self._onNodeClick) self._onNodeClick(this.dataset.id);
      });
    });
  };

  // ── KGLatentView public API ────────────────────────────────────────────────
  KGLatentView.prototype.setData = function (kg) {
    this._kg = kg || { nodes: [], edges: [] };
    this._render();
  };

  KGLatentView.prototype.setFilter = function (nodeTypes) {
    this._activeNodeTypes = nodeTypes || null;
    this._render();
  };

  KGLatentView.prototype.setTheme = function (theme) {
    this._theme = theme;
    this._container.className = 'kgc-latent ' + (theme !== 'light' ? 'kgc-dark' : 'kgc-light');
    this._render();
  };

  KGLatentView.prototype.highlightNode = function (nodeId) {
    if (!this._svgEl) return;
    this._svgEl.querySelectorAll('.kgc-latent-dot').forEach(d => {
      d.classList.toggle('kgc-selected', d.dataset.id === nodeId);
    });
  };

  KGLatentView.prototype.destroy = function () {
    this._container.innerHTML = '';
  };

  // ════════════════════════════════════════════════════════════════════════════
  // KGAggregateView — node/edge statistics
  //
  // Shows:
  //   - Node counts per semantic layer (horizontal bar chart)
  //   - Top edge types by count (horizontal bar chart)
  //
  // Usage (standalone):
  //   const a = new KGAggregateView(el, kg, { theme:'dark' });
  //   a.setFilter(nodeTypeSet);
  // ════════════════════════════════════════════════════════════════════════════
  function KGAggregateView(containerEl, kg, opts) {
    opts = Object.assign({ theme: 'dark' }, opts || {});
    this._container      = containerEl;
    this._kg             = kg || { nodes: [], edges: [] };
    this._opts           = opts;
    this._theme          = opts.theme;
    this._activeNodeTypes = null;
    this._buildDOM();
    this._render();
  }

  KGAggregateView.prototype._buildDOM = function () {
    this._container.className = 'kgc-aggregate ' + (this._theme !== 'light' ? 'kgc-dark' : 'kgc-light');
    this._container.innerHTML = '<div class="kgc-agg-body"></div>';
    this._bodyEl = this._container.querySelector('.kgc-agg-body');
  };

  KGAggregateView.prototype._render = function () {
    const kg    = this._kg;
    const nodes = (kg.nodes || []).filter(n => {
      if (!this._activeNodeTypes) return true;
      return this._activeNodeTypes.has(n.node_type);
    });
    const edges = kg.edges || [];

    // Node counts per layer
    const layerCounts = {};
    LAYERS.forEach(l => { layerCounts[l.id] = { count: 0, label: l.label, icon: l.icon, color: l.color }; });
    nodes.forEach(n => {
      const lid = TYPE_TO_LAYER[n.node_type];
      if (lid && layerCounts[lid]) layerCounts[lid].count++;
    });

    // Edge counts per type (top 8)
    const edgeCounts = {};
    edges.forEach(e => {
      const rel = e.relation || e.type || e.label || e.edge_type || '(unlabeled)';
      edgeCounts[rel] = (edgeCounts[rel] || 0) + 1;
    });
    const topEdges = Object.entries(edgeCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);

    const maxNodeCount = Math.max(1, ...LAYERS.map(l => layerCounts[l.id].count));
    const isDark = this._theme !== 'light';
    const mutedColor = isDark ? '#334155' : '#cbd5e1';

    let html =
      '<div class="kgc-agg-section">'
      + '<div class="kgc-agg-section-title">Nodes by Layer (' + nodes.length + ' total)</div>'
      + LAYERS.map(l => {
          const c   = layerCounts[l.id].count;
          const pct = Math.round((c / maxNodeCount) * 100);
          return '<div class="kgc-agg-row">'
            + '<div class="kgc-agg-row-label">'
            + '<span class="kgc-agg-icon">' + l.icon + '</span>'
            + '<span>' + esc(l.label) + '</span>'
            + '</div>'
            + '<div class="kgc-agg-bar-wrap">'
            + '<div class="kgc-agg-bar" style="width:' + pct + '%;background:' + l.color + '"></div>'
            + '</div>'
            + '<div class="kgc-agg-count">' + c + '</div>'
            + '</div>';
        }).join('')
      + '</div>';

    if (topEdges.length) {
      const maxEdge = Math.max(1, topEdges[0][1]);
      html +=
        '<div class="kgc-agg-section">'
        + '<div class="kgc-agg-section-title">Edge Types (' + edges.length + ' total)</div>'
        + topEdges.map(([rel, cnt]) => {
            const pct = Math.round((cnt / maxEdge) * 100);
            return '<div class="kgc-agg-row">'
              + '<div class="kgc-agg-row-label"><span>' + esc(rel) + '</span></div>'
              + '<div class="kgc-agg-bar-wrap">'
              + '<div class="kgc-agg-bar" style="width:' + pct + '%;background:' + mutedColor + '"></div>'
              + '</div>'
              + '<div class="kgc-agg-count">' + cnt + '</div>'
              + '</div>';
          }).join('')
        + '</div>';
    }

    this._bodyEl.innerHTML = html;
  };

  // ── KGAggregateView public API ─────────────────────────────────────────────
  KGAggregateView.prototype.setData = function (kg) {
    this._kg = kg || { nodes: [], edges: [] };
    this._render();
  };

  KGAggregateView.prototype.setFilter = function (nodeTypes) {
    this._activeNodeTypes = nodeTypes || null;
    this._render();
  };

  KGAggregateView.prototype.setTheme = function (theme) {
    this._theme = theme;
    this._container.className = 'kgc-aggregate ' + (theme !== 'light' ? 'kgc-dark' : 'kgc-light');
    this._render();
  };

  KGAggregateView.prototype.destroy = function () { this._container.innerHTML = ''; };

  // ════════════════════════════════════════════════════════════════════════════
  // KGComposer — main compositor
  //
  // Options:
  //   kg_view:        true / false   — show KG graph pane (default: true)
  //   latent_view:    true / false   — show latent space pane (default: false)
  //   aggregate_view: true / false   — show stats pane (default: false)
  //   compare_view:   true / false   — show compare pane placeholder (default: false)
  //   filter_panel:   'matrix' | 'layered' | 'flat' | false
  //                                  — filter panel style (default: 'matrix')
  //   filter_schema:  true / false   — show schema nodes in filter (default: true)
  //   panel_mode:     'open' | 'closed'  (default: 'open')
  //   theme:          'dark' | 'light' | 'auto'  (default: 'dark')
  //   layout:         'dagre-tb' | 'dagre-lr' | 'breadthfirst' | 'cose-bilkent'
  //   hover:          true / false   — hover tooltips (default: true)
  //   title:          string
  //   preset:         string         — initial named preset ID
  //   maxNodes:       number         (default: 300)
  // ════════════════════════════════════════════════════════════════════════════
  function KGComposer(containerEl, kg, opts) {
    opts = Object.assign({
      kg_view:        true,
      latent_view:    false,
      aggregate_view: false,
      compare_view:   false,
      filter_panel:   'matrix',
      filter_schema:  true,
      panel_mode:     'open',
      theme:          'dark',
      layout:         'dagre-tb',
      hover:          true,
      title:          '',
      preset:         null,
      maxNodes:       300,
    }, opts || {});

    this._container = containerEl;
    this._kg        = kg || { nodes: [], edges: [] };
    this._opts      = opts;
    this._theme     = opts.theme === 'auto'
      ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : opts.theme;

    this._graph     = null;
    this._filter    = null;
    this._latent    = null;
    this._aggregate = null;
    this._useKGWidget = false;

    // Determine first active view
    const hasPanes = [opts.kg_view, opts.latent_view, opts.aggregate_view, opts.compare_view];
    if (!hasPanes.some(Boolean)) opts.kg_view = true;
    this._activeView = opts.kg_view ? 'graph'
      : opts.latent_view ? 'latent'
      : opts.aggregate_view ? 'aggregate' : 'compare';

    containerEl.classList.add('kgc-composer');
    this._applyTheme();
    this._buildShell();
    this._initFilter();
    this._initViews();

    // Apply preset after all views are ready
    if (opts.preset) {
      this._applyPreset(opts.preset);
    } else {
      this._onFilterChange(this._filter ? this._filter.getState() : null);
    }
  }

  KGComposer.prototype._applyTheme = function () {
    this._container.dataset.theme = this._theme;
  };

  KGComposer.prototype._buildShell = function () {
    const opts     = this._opts;
    const showPanel = opts.filter_panel && opts.filter_panel !== 'none';
    const panelOpen = opts.panel_mode !== 'closed';

    const views = [];
    if (opts.kg_view)        views.push({ id: 'graph',     label: 'Graph' });
    if (opts.latent_view)    views.push({ id: 'latent',    label: 'Latent' });
    if (opts.aggregate_view) views.push({ id: 'aggregate', label: 'Stats' });
    if (opts.compare_view)   views.push({ id: 'compare',   label: 'Compare' });

    const tabsHTML = views.length > 1
      ? '<div class="kgc-tabs">'
        + views.map(v =>
            '<button class="kgc-tab' + (v.id === this._activeView ? ' active' : '')
            + '" data-view="' + v.id + '">' + v.label + '</button>'
          ).join('')
        + '</div>'
      : '';

    const panesHTML = views.map(v =>
      '<div class="kgc-pane' + (v.id === this._activeView ? ' active' : '')
      + '" data-pane="' + v.id + '"><div class="kgc-pane-inner"></div></div>'
    ).join('');

    this._container.innerHTML =
      (showPanel
        ? '<div class="kgc-panel' + (panelOpen ? '' : ' collapsed') + '">'
          + '<div class="kgc-panel-inner"></div>'
          + '</div>'
          + '<div class="kgc-resize-handle" title="Drag to resize"></div>'
        : '')
      + '<div class="kgc-main">'
      + tabsHTML
      + '<div class="kgc-panes">' + panesHTML + '</div>'
      + '</div>';

    this._panelEl      = this._container.querySelector('.kgc-panel');
    this._panelInnerEl = this._container.querySelector('.kgc-panel-inner');
    this._tabsEl       = this._container.querySelector('.kgc-tabs');
    this._panesEl      = this._container.querySelector('.kgc-panes');

    const self = this;

    // ── Drag-resize panel ──────────────────────────────────────────────────
    var resizeHandle = this._container.querySelector('.kgc-resize-handle');
    if (resizeHandle && this._panelEl) {
      resizeHandle.addEventListener('mousedown', function (e) {
        e.preventDefault();
        var startX = e.clientX;
        var startW = self._panelEl.offsetWidth;
        resizeHandle.classList.add('dragging');
        function onMove(e) {
          var newW = Math.max(150, Math.min(500, startW + e.clientX - startX));
          self._panelEl.style.width    = newW + 'px';
          self._panelEl.style.minWidth = newW + 'px';
        }
        function onUp() {
          resizeHandle.classList.remove('dragging');
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup',   onUp);
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup',   onUp);
      });
    }

    // Bind tab switching
    if (this._tabsEl) {
      this._tabsEl.addEventListener('click', function (evt) {
        const tab = evt.target.closest('.kgc-tab');
        if (tab) self._switchView(tab.dataset.view);
      });
    }
  };

  KGComposer.prototype._switchView = function (viewId) {
    this._activeView = viewId;
    this._container.querySelectorAll('.kgc-tab').forEach(t =>
      t.classList.toggle('active', t.dataset.view === viewId)
    );
    this._container.querySelectorAll('.kgc-pane').forEach(p =>
      p.classList.toggle('active', p.dataset.pane === viewId)
    );
  };

  KGComposer.prototype._getPaneInner = function (viewId) {
    const pane = this._container.querySelector('[data-pane="' + viewId + '"] .kgc-pane-inner');
    return pane || null;
  };

  KGComposer.prototype._initFilter = function () {
    const opts = this._opts;
    if (!opts.filter_panel || !this._panelInnerEl) return;

    const self = this;

    if (opts.filter_panel === 'matrix') {
      this._filter = new KGFilterMatrix(this._panelInnerEl, this._kg, {
        theme:    this._theme,
        preset:   opts.preset,
        onChange: function (state) { self._onFilterChange(state); },
      });
    } else {
      // 'layered' or 'flat' → delegate to KGWidget's built-in panel
      this._useKGWidget = true;
    }

    // Build panel-toggle button (injected into KGGraph toolbar after init)
    this._panelToggleBtn = document.createElement('button');
    this._panelToggleBtn.className = 'kg-btn kg-btn-icon kgc-panel-toggle';
    this._panelToggleBtn.title     = 'Toggle filter panel';
    this._panelToggleBtn.innerHTML = '&#9776;';
    this._panelToggleBtn.addEventListener('click', function () {
      if (self._panelEl) self._panelEl.classList.toggle('collapsed');
    });
  };

  KGComposer.prototype._initViews = function () {
    const opts = this._opts;

    // ── Graph view ──────────────────────────────────────────────────────────
    if (opts.kg_view !== false) {
      const el = this._getPaneInner('graph');
      if (el) {
        if (this._useKGWidget && window.KGWidget) {
          // KGWidget manages its own filter panel internally
          this._graph = new window.KGWidget(el, this._kg, {
            theme:       this._theme,
            layout:      opts.layout,
            maxNodes:    opts.maxNodes,
            title:       opts.title,
            panelMode:   opts.panel_mode,
            filterStyle: opts.filter_panel === 'matrix' ? 'flat' : (opts.filter_panel || 'layered'),
          });
        } else if (window.KGGraph) {
          this._graph = new window.KGGraph(el, this._kg, {
            theme:    this._theme,
            layout:   opts.layout,
            maxNodes: opts.maxNodes,
            title:    opts.title,
          });
          // Inject panel-toggle into the graph toolbar
          if (this._panelToggleBtn && this._graph.toolbarLeftEl) {
            this._graph.toolbarLeftEl.insertBefore(
              this._panelToggleBtn,
              this._graph.toolbarLeftEl.firstChild,
            );
          }
        }
      }
    }

    // ── Latent view ─────────────────────────────────────────────────────────
    if (opts.latent_view) {
      const el = this._getPaneInner('latent');
      if (el) {
        const self = this;
        this._latent = new KGLatentView(el, this._kg, {
          theme: this._theme,
          onNodeClick: function (nodeId) {
            // Cross-highlight: latent dot → graph node
            if (self._graph && self._graph._highlightNeighborhood) {
              self._graph._highlightNeighborhood(nodeId, 'focus');
            }
            // Switch to graph view so user sees the highlight
            if (self._opts.kg_view) self._switchView('graph');
          },
        });
      }
    }

    // ── Aggregate view ───────────────────────────────────────────────────────
    if (opts.aggregate_view) {
      const el = this._getPaneInner('aggregate');
      if (el) {
        this._aggregate = new KGAggregateView(el, this._kg, {
          theme: this._theme,
        });
      }
    }

    // ── Compare view (placeholder) ───────────────────────────────────────────
    if (opts.compare_view) {
      const el = this._getPaneInner('compare');
      if (el) {
        el.innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;height:100%;'
          + 'color:#64748b;font-size:12px;">Compare view — coming soon</div>';
      }
    }
  };

  // ── Filter state → all views ────────────────────────────────────────────────
  KGComposer.prototype._onFilterChange = function (state) {
    if (!state) {
      if (this._graph && !this._useKGWidget) this._graph.setFilter(null, null);
      if (this._latent)    this._latent.setFilter(null);
      if (this._aggregate) this._aggregate.setFilter(null);
      return;
    }

    // Support both new {layers,blocks,spans} and legacy flat {layerId,...} state
    var layerState = state.layers || state;

    // 1. Active node types from layers
    var activeNodeTypes = new Set();
    LAYERS.forEach(function (l) {
      var ls = layerState[l.id];
      if (ls && ls.nodes) l.types.forEach(function (t) { activeNodeTypes.add(t); });
    });
    var allNodesOn = LAYERS.every(function (l) { return !layerState[l.id] || layerState[l.id].nodes; });

    // 2. Edge filter
    var edgeFilter = function (srcType, tgtType) {
      var srcLid = TYPE_TO_LAYER[srcType];
      var tgtLid = TYPE_TO_LAYER[tgtType];
      var srcSt  = layerState[srcLid] || { innerEdges: true, outerEdges: true };
      var tgtSt  = layerState[tgtLid] || { innerEdges: true, outerEdges: true };
      if (srcLid === tgtLid) {
        return srcSt.innerEdges !== false && tgtSt.innerEdges !== false;
      }
      return srcSt.outerEdges !== false && tgtSt.outerEdges !== false;
    };

    // 3. Group layers
    var groupLayers = new Set();
    LAYERS.forEach(function (l) {
      if (layerState[l.id] && layerState[l.id].group) groupLayers.add(l.id);
    });

    // 4. Push to graph
    if (this._graph && !this._useKGWidget) {
      this._graph.setFilter(allNodesOn ? null : activeNodeTypes, null);
      if (this._graph.setEdgeFilter)  this._graph.setEdgeFilter(edgeFilter);
      if (this._graph.setGroupLayers) this._graph.setGroupLayers(groupLayers.size > 0 ? groupLayers : null);
    }

    // 5. Push to other views
    if (this._latent)    this._latent.setFilter(allNodesOn ? null : activeNodeTypes);
    if (this._aggregate) this._aggregate.setFilter(allNodesOn ? null : activeNodeTypes);
  };

  KGComposer.prototype._applyPreset = function (presetId) {
    if (this._filter && this._filter.applyPreset) {
      // Filter panel present — it will call onChange which updates the graph
      this._filter.applyPreset(presetId);
    } else if (this._useKGWidget && this._graph && this._graph._applyPreset) {
      this._graph._applyPreset(presetId);
    } else {
      // No filter panel (filter_panel: false) — apply preset state directly
      var state = makeFullState();
      applyPresetToState(state, presetId);
      this._onFilterChange(state);
    }
  };

  // ── KGComposer public API ──────────────────────────────────────────────────
  KGComposer.prototype.setData = function (kg) {
    this._kg = kg || { nodes: [], edges: [] };
    if (this._graph)     this._graph.setData(this._kg);
    if (this._filter)    this._filter.setData(this._kg);
    if (this._latent)    this._latent.setData(this._kg);
    if (this._aggregate) this._aggregate.setData(this._kg);
  };

  KGComposer.prototype.setTheme = function (theme) {
    this._theme = theme;
    this._container.dataset.theme = theme;
    if (this._graph)     this._graph.setTheme(theme);
    if (this._filter)    this._filter.setTheme(theme);
    if (this._latent)    this._latent.setTheme(theme);
    if (this._aggregate) this._aggregate.setTheme(theme);
  };

  KGComposer.prototype.applyPreset = function (presetId) {
    this._applyPreset(presetId);
  };

  KGComposer.prototype.openPanel = function () {
    if (this._panelEl) this._panelEl.classList.remove('collapsed');
  };

  KGComposer.prototype.closePanel = function () {
    if (this._panelEl) this._panelEl.classList.add('collapsed');
  };

  KGComposer.prototype.destroy = function () {
    if (this._graph     && this._graph.destroy)     this._graph.destroy();
    if (this._latent    && this._latent.destroy)    this._latent.destroy();
    if (this._aggregate && this._aggregate.destroy) this._aggregate.destroy();
    this._container.innerHTML = '';
    this._container.classList.remove('kgc-composer');
    delete this._container.dataset.theme;
  };

  // ── Module exports ─────────────────────────────────────────────────────────
  global.KGFilterMatrix        = KGFilterMatrix;
  global.KGLatentView          = KGLatentView;
  global.KGAggregateView       = KGAggregateView;
  global.KGComposer            = KGComposer;
  global.KGComposerPresets     = COMPOSER_PRESETS;
  global.applyComposerPreset   = applyPresetToState;

}(typeof window !== 'undefined' ? window : this));
