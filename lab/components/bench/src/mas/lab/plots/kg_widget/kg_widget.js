//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
/**
 * KGWidget — MAS Knowledge-Graph visualiser v2 (Cytoscape.js)
 *
 * Usage:
 *   const w = new KGWidget(containerEl, kgData, { theme:'dark', layout:'dagre', title:'' });
 *   w.setData(newKg);   w.setTheme('light');   w.destroy();
 *
 * CDN deps: cytoscape, cytoscape-dagre, dagre, cytoscape-cose-bilkent,
 *           layout-base, cose-base, cytoscape-svg
 */
(function (global) {
  'use strict';

  // ─── Semantic layers ───────────────────────────────────────────────────────
  const LAYERS = [
    { id: 'execution',  label: 'Execution',  icon: '⚙',  color: '#475569', types: ['Session','Run'] },
    { id: 'agent',      label: 'Agents',     icon: '🤖', color: '#7c3aed', types: ['Agent','Worker'] },
    { id: 'call',       label: 'Calls',      icon: '↺',  color: '#2563eb', types: ['MASCall','AgentCall','LLMCall','ToolCall','ProcessingCall','RAGQuery','MemoryCall','TaskCall','NetworkCall'] },
    { id: 'memory',     label: 'Memory',     icon: '◈',  color: '#10b981', types: ['State','Transition'] },
    { id: 'resource',   label: 'Resources',  icon: '⬡',  color: '#ea580c', types: ['Tool','LLM','Skill'] },
    { id: 'governance', label: 'Governance', icon: '🛡', color: '#dc2626', types: ['GovernanceEvent','PolicyDenial','PolicyAllow','HITLGate','BudgetEvent','ControlIntervention','TransformationEvent'] },
    { id: 'annotation', label: 'Annotations',icon: '📌', color: '#64748b', types: ['CallAnnotation'] },
    { id: 'structural', label: 'Structural', icon: '⬡', color: '#0891b2', types: ['ParallelGroup','Branch'] },
  ];
  const TYPE_TO_LAYER = {};
  LAYERS.forEach(l => l.types.forEach(t => { TYPE_TO_LAYER[t] = l.id; }));

  // ─── Node visual styles ────────────────────────────────────────────────────
  // Shape convention: roundrectangle = entities (things that exist)
  //                    ellipse        = events/actions (things that happen)
  const NODE_DARK = {
    Session:        { bg:'#1e293b', fg:'#94a3b8', border:'#475569', shape:'roundrectangle', size:44 },
    Run:            { bg:'#1e3a5f', fg:'#60a5fa', border:'#2563eb', shape:'roundrectangle', size:34 },
    Agent:          { bg:'#3b0764', fg:'#c084fc', border:'#7c3aed', shape:'roundrectangle', size:36 },
    Worker:         { bg:'#4c1d95', fg:'#ddd6fe', border:'#7c3aed', shape:'roundrectangle', size:28 },
    MASCall:        { bg:'#1e3a5f', fg:'#93c5fd', border:'#3b82f6', shape:'ellipse',         size:26 },
    AgentCall:      { bg:'#1d4ed8', fg:'#bfdbfe', border:'#60a5fa', shape:'ellipse',         size:24 },
    LLMCall:        { bg:'#0c4a6e', fg:'#7dd3fc', border:'#0284c7', shape:'ellipse',         size:24 },
    ToolCall:       { bg:'#78350f', fg:'#fde68a', border:'#d97706', shape:'ellipse',         size:24 },
    ProcessingCall: { bg:'#1e3a5f', fg:'#a5b4fc', border:'#6366f1', shape:'ellipse',         size:22 },
    State:          { bg:'#064e3b', fg:'#34d399', border:'#10b981', shape:'roundrectangle', size:28 },
    Transition:     { bg:'#14532d', fg:'#86efac', border:'#22c55e', shape:'ellipse',         size:20 },
    Tool:           { bg:'#451a03', fg:'#fb923c', border:'#ea580c', shape:'roundrectangle', size:30 },
    LLM:            { bg:'#0c4a6e', fg:'#38bdf8', border:'#0284c7', shape:'roundrectangle', size:30 },
    Skill:              { bg:'#2d1b69', fg:'#a78bfa', border:'#7c3aed', shape:'roundrectangle', size:30 },
    RAGQuery:           { bg:'#1c3a4f', fg:'#67e8f9', border:'#06b6d4', shape:'ellipse',         size:22 },
    MemoryCall:         { bg:'#064e3b', fg:'#34d399', border:'#10b981', shape:'ellipse',         size:22 },
    TaskCall:           { bg:'#1e3a5f', fg:'#93c5fd', border:'#3b82f6', shape:'ellipse',         size:22 },
    NetworkCall:        { bg:'#1c3a4f', fg:'#a5f3fc', border:'#22d3ee', shape:'ellipse',         size:22 },
    GovernanceEvent:    { bg:'#451a03', fg:'#fdba74', border:'#f97316', shape:'ellipse',         size:22 },
    PolicyDenial:       { bg:'#450a0a', fg:'#fca5a5', border:'#ef4444', shape:'ellipse',         size:22 },
    PolicyAllow:        { bg:'#052e16', fg:'#86efac', border:'#22c55e', shape:'ellipse',         size:22 },
    HITLGate:           { bg:'#2e1065', fg:'#e9d5ff', border:'#a855f7', shape:'ellipse',         size:22 },
    BudgetEvent:        { bg:'#422006', fg:'#fde68a', border:'#f59e0b', shape:'ellipse',         size:22 },
    ControlIntervention:{ bg:'#450a0a', fg:'#fbb0b0', border:'#dc2626', shape:'ellipse',         size:22 },
    TransformationEvent:{ bg:'#042f2e', fg:'#99f6e4', border:'#14b8a6', shape:'ellipse',         size:22 },
    CallAnnotation:     { bg:'#1e293b', fg:'#94a3b8', border:'#475569', shape:'roundrectangle', size:18 },
    ParallelGroup:      { bg:'#1e3a5f', fg:'#a5b4fc', border:'#6366f1', shape:'roundrectangle', size:26 },
    Branch:             { bg:'#1c3a4f', fg:'#67e8f9', border:'#06b6d4', shape:'roundrectangle', size:24 },
  };
  const NODE_DARK_DEFAULT = { bg:'#1e293b', fg:'#94a3b8', border:'#475569', shape:'ellipse', size:20 };

  const NODE_LIGHT = {
    Session:        { bg:'#f1f5f9', fg:'#334155', border:'#94a3b8', shape:'roundrectangle', size:44 },
    Run:            { bg:'#eff6ff', fg:'#1d4ed8', border:'#93c5fd', shape:'roundrectangle', size:34 },
    Agent:          { bg:'#faf5ff', fg:'#7c3aed', border:'#c084fc', shape:'roundrectangle', size:36 },
    Worker:         { bg:'#ede9fe', fg:'#4c1d95', border:'#a78bfa', shape:'roundrectangle', size:28 },
    MASCall:        { bg:'#eff6ff', fg:'#1e40af', border:'#93c5fd', shape:'ellipse',         size:26 },
    AgentCall:      { bg:'#dbeafe', fg:'#1d4ed8', border:'#60a5fa', shape:'ellipse',         size:24 },
    LLMCall:        { bg:'#e0f2fe', fg:'#0369a1', border:'#38bdf8', shape:'ellipse',         size:24 },
    ToolCall:       { bg:'#fef3c7', fg:'#92400e', border:'#fbbf24', shape:'ellipse',         size:24 },
    ProcessingCall: { bg:'#eef2ff', fg:'#3730a3', border:'#818cf8', shape:'ellipse',         size:22 },
    State:          { bg:'#d1fae5', fg:'#065f46', border:'#34d399', shape:'roundrectangle', size:28 },
    Transition:     { bg:'#dcfce7', fg:'#14532d', border:'#86efac', shape:'ellipse',         size:20 },
    Tool:           { bg:'#fff7ed', fg:'#9a3412', border:'#fb923c', shape:'roundrectangle', size:30 },
    LLM:            { bg:'#e0f2fe', fg:'#075985', border:'#38bdf8', shape:'roundrectangle', size:30 },
    Skill:              { bg:'#ede9fe', fg:'#4c1d95', border:'#a78bfa', shape:'roundrectangle', size:30 },
    RAGQuery:           { bg:'#ecfeff', fg:'#0e7490', border:'#22d3ee', shape:'ellipse',         size:22 },
    MemoryCall:         { bg:'#d1fae5', fg:'#065f46', border:'#34d399', shape:'ellipse',         size:22 },
    TaskCall:           { bg:'#eff6ff', fg:'#1e40af', border:'#93c5fd', shape:'ellipse',         size:22 },
    NetworkCall:        { bg:'#ecfeff', fg:'#155e75', border:'#67e8f9', shape:'ellipse',         size:22 },
    GovernanceEvent:    { bg:'#fff7ed', fg:'#9a3412', border:'#fb923c', shape:'ellipse',         size:22 },
    PolicyDenial:       { bg:'#fef2f2', fg:'#991b1b', border:'#fca5a5', shape:'ellipse',         size:22 },
    PolicyAllow:        { bg:'#f0fdf4', fg:'#14532d', border:'#86efac', shape:'ellipse',         size:22 },
    HITLGate:           { bg:'#faf5ff', fg:'#6b21a8', border:'#d8b4fe', shape:'ellipse',         size:22 },
    BudgetEvent:        { bg:'#fffbeb', fg:'#92400e', border:'#fcd34d', shape:'ellipse',         size:22 },
    ControlIntervention:{ bg:'#fef2f2', fg:'#b91c1c', border:'#f87171', shape:'ellipse',         size:22 },
    TransformationEvent:{ bg:'#f0fdfa', fg:'#115e59', border:'#5eead4', shape:'ellipse',         size:22 },
    CallAnnotation:     { bg:'#f8fafc', fg:'#475569', border:'#94a3b8', shape:'roundrectangle', size:18 },
    ParallelGroup:      { bg:'#eef2ff', fg:'#3730a3', border:'#818cf8', shape:'roundrectangle', size:26 },
    Branch:             { bg:'#ecfeff', fg:'#0e7490', border:'#22d3ee', shape:'roundrectangle', size:24 },
  };
  const NODE_LIGHT_DEFAULT = { bg:'#f8fafc', fg:'#334155', border:'#94a3b8', shape:'ellipse', size:20 };

  const EDGE_COLOR_DARK  = '#334155';
  const EDGE_COLOR_LIGHT = '#94a3b8';

  // ─── Schema reference ─────────────────────────────────────────────────────
  const SCHEMA = {
    Session:        { desc: 'Top-level session container', fields: ['sessionId','runId','inputQuery','finalResponse','startTime','endTime'] },
    Run:            { desc: 'A single run within a session', fields: ['runId'] },
    Agent:          { desc: 'An agent in the MAS', fields: ['agentId'] },
    MASCall:        { desc: 'Root call to the MAS system', fields: ['callId','masName','masType','startTime','endTime','status'] },
    AgentCall:      { desc: 'A call to a specific agent', fields: ['callId','agentId','agentName','agentType','inputContent','outputContent','startTime','endTime','status'] },
    LLMCall:        { desc: 'LLM inference call', fields: ['callId','modelName','prompt','completion','promptTokenCount','completionTokenCount','finishReason','startTime','endTime'] },
    ToolCall:       { desc: 'External tool invocation', fields: ['callId','toolName','toolArguments','toolOutput','startTime','endTime','status'] },
    ProcessingCall: { desc: 'Internal processing step', fields: ['callId','processingName','processingType','startTime','endTime'] },
    State:          { desc: 'Memory/state node in the agent context', fields: ['stateNodeId','semanticType','deltaType','content','contentHash','sourceCallId'] },
    Transition:          { desc: 'State transition in the execution trace', fields: ['transitionId','fromState','toState','actionType','appliedOperator','realizesCallId','transitionTimestamp'] },
    Tool:                { desc: 'Tool resource definition', fields: ['name','masUri','block','callCount'] },
    LLM:                 { desc: 'LLM resource definition', fields: ['name','masUri','block','callCount'] },
    Skill:               { desc: 'Skill resource definition', fields: ['name','masUri','block','callCount'] },
    RAGQuery:            { desc: 'Retrieval-augmented generation query call', fields: ['callId','agentId','queryText','retrievedDocCount','startTime','endTime','status'] },
    MemoryCall:          { desc: 'Memory read/write operation', fields: ['callId','agentId','memoryType','operation','startTime','endTime','status'] },
    TaskCall:            { desc: 'Task dispatch to sub-agent or system', fields: ['callId','agentId','taskName','startTime','endTime','status'] },
    NetworkCall:         { desc: 'External network/API call', fields: ['callId','agentId','url','method','statusCode','startTime','endTime'] },
    GovernanceEvent:     { desc: 'Governance check event (policy evaluated)', fields: ['callId','hook','contractId','decision','reason','timestamp'] },
    PolicyDenial:        { desc: 'Governance policy denial (access blocked)', fields: ['callId','hook','contractId','reason','decisionType','details','timestamp'] },
    PolicyAllow:         { desc: 'Governance policy allow (access permitted)', fields: ['callId','hook','contractId','reason','decisionType','timestamp'] },
    HITLGate:            { desc: 'Human-in-the-loop approval gate', fields: ['callId','agentId','prompt','approved','respondedBy','timestamp'] },
    BudgetEvent:         { desc: 'Budget limit check or exhaustion event', fields: ['callId','agentId','budgetKind','limit','consumed','timestamp'] },
    ControlIntervention: { desc: 'Runtime control-plane intervention', fields: ['callId','interventionType','reason','timestamp'] },
    TransformationEvent: { desc: 'Data transformation step in pipeline', fields: ['callId','transformType','inputType','outputType','timestamp'] },
    CallAnnotation:      { desc: 'Annotation attached to a call (routing result, user I/O, compaction)', fields: ['callId','annotationKind','content','timestamp'] },
    ParallelGroup:       { desc: 'Group of calls executing in parallel', fields: ['groupId','agentId','branchCount','startTime','endTime'] },
    Branch:              { desc: 'One branch within a parallel group', fields: ['branchId','groupId','branchIndex','startTime','endTime','status'] },
  };

  // ─── Layouts ───────────────────────────────────────────────────────────────
  const LAYOUTS = {
    'dagre-tb':     { name:'dagre',        rankDir:'TB', spacingFactor:1.3, padding:24 },
    'dagre-lr':     { name:'dagre',        rankDir:'LR', spacingFactor:1.3, padding:24 },
    'breadthfirst': { name:'breadthfirst', directed:true, spacingFactor:1.2, padding:20 },
    'cose-bilkent': { name:'cose-bilkent', idealEdgeLength:90, nodeRepulsion:8000, animate:false },
  };

  // ─── Filter presets ────────────────────────────────────────────────────────
  const PRESETS = [
    { id:'all',       label:'Show all',       desc:'All node and edge types', nodes:null, edges:null },
    { id:'calls',     label:'Calls only',     desc:'All *Call nodes + edges', nodes:['MASCall','AgentCall','LLMCall','ToolCall','ProcessingCall'], edges:null },
    { id:'llm-trace', label:'LLM trace',      desc:'Agents + LLM calls + States', nodes:['Agent','AgentCall','LLMCall','State'], edges:null },
    { id:'memory',    label:'Memory flow',    desc:'State + Transition only', nodes:['State','Transition'], edges:null },
    { id:'resources',   label:'Resources',   desc:'Tool / LLM / Skill + their calls', nodes:['Tool','LLM','Skill','ToolCall','LLMCall'], edges:null },
    { id:'top-level',   label:'Top-level',   desc:'Session + Run + Agents only', nodes:['Session','Run','Agent'], edges:null },
    { id:'governance',  label:'Governance',  desc:'Governance, policy, and HITL nodes', nodes:['GovernanceEvent','PolicyDenial','PolicyAllow','HITLGate','BudgetEvent','ControlIntervention','TransformationEvent','AgentCall'], edges:null },
    { id:'failures',    label:'Failures',    desc:'Failed calls + PolicyDenial nodes', nodes:['PolicyDenial','ControlIntervention','AgentCall','MASCall'], edges:null },
  ];

  // ─── Helpers ───────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;');
  }

  function shortLabel(n) {
    // Keys tried in order — only used when value differs from n.id
    // (prevents "session-events" or "events" from appearing as labels when
    //  those are just auto-generated IDs that equal the node's id field)
    const keys = ['agentName','agentId','name','toolName','llmName','modelName',
                  'processingName','masName','label','callId','stateNodeId',
                  'inputQuery','semanticType'];
    for (const k of keys) {
      const v = n[k];
      if (v && String(v) !== (n.id || '')) {
        const s = String(v);
        return s.length > 20 ? s.slice(0,19) + '\u2026' : s;
      }
    }
    // Prefer the ontology type name over the raw id (which is often an
    // auto-generated run-scoped identifier like "session-events" or "events")
    const fallback = n.node_type || n.id || '?';
    return fallback.length > 20 ? fallback.slice(0,19) + '\u2026' : fallback;
  }

  // ─── Compact hover tooltip text (type + 2-5 key facts) ───────────────────
  function shortTip(n) {
    if (!n) return '';
    const t = n.node_type || '';
    const lines = [];

    if (t === 'LLMCall') {
      if (n.modelName)  lines.push('Model: ' + n.modelName);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
      const pt = n.promptTokenCount || 0;
      const ct = n.completionTokenCount || 0;
      if (pt || ct) lines.push('Tokens: ' + pt + ' prompt / ' + ct + ' completion');
      if (n.status)     lines.push('Status: ' + n.status);
      if (n.finishReason) lines.push('Finish: ' + n.finishReason);
    } else if (t === 'ToolCall') {
      if (n.toolName) lines.push('Tool: ' + n.toolName);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
      if (n.status) lines.push('Status: ' + n.status);
    } else if (t === 'AgentCall') {
      const lbl = n.agentName || n.agentId;
      if (lbl) lines.push('Agent: ' + lbl);
      if (n.agentType) lines.push('Type: ' + n.agentType);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
      if (n.status) lines.push('Status: ' + n.status);
    } else if (t === 'State') {
      if (n.semanticType) lines.push('Type: ' + n.semanticType);
      if (n.deltaType)    lines.push('Delta: ' + n.deltaType);
      if (n.stateNodeId && n.stateNodeId !== n.id) lines.push('Node: ' + n.stateNodeId);
    } else if (t === 'Session') {
      if (n.inputQuery) lines.push('Query: ' + String(n.inputQuery).slice(0, 80));
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
    } else if (t === 'Run') {
      if (n.runId && n.runId !== n.id) lines.push('Run: ' + n.runId);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
    } else if (t === 'Agent' || t === 'Worker') {
      if (n.agentId)   lines.push('ID: ' + n.agentId);
      if (n.agentType) lines.push('Type: ' + n.agentType);
      if (n.agentName) lines.push('Name: ' + n.agentName);
    } else if (t === 'MASCall') {
      if (n.masName) lines.push('MAS: ' + n.masName);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
      if (n.status) lines.push('Status: ' + n.status);
    } else if (t === 'Tool' || t === 'LLM' || t === 'Skill') {
      if (n.name)            lines.push('Name: ' + n.name);
      if (n.masUri)          lines.push('URI: ' + n.masUri);
      if (n.callCount != null) lines.push('Calls: ' + n.callCount);
    } else if (t === 'Transition') {
      if (n.actionType)      lines.push('Action: ' + n.actionType);
      if (n.appliedOperator) lines.push('Operator: ' + n.appliedOperator);
    } else if (t === 'ProcessingCall') {
      if (n.processingName) lines.push('Name: ' + n.processingName);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
    } else if (t === 'PolicyDenial' || t === 'GovernanceEvent') {
      if (n.contractId) lines.push('Contract: ' + n.contractId);
      if (n.hook)       lines.push('Hook: ' + n.hook);
      if (n.reason)     lines.push('Reason: ' + String(n.reason).slice(0, 80));
      if (n.decisionType) lines.push('Decision: ' + n.decisionType);
    } else if (t === 'PolicyAllow') {
      if (n.contractId) lines.push('Contract: ' + n.contractId);
      if (n.hook)       lines.push('Hook: ' + n.hook);
      if (n.reason)     lines.push('Reason: ' + String(n.reason).slice(0, 80));
    } else if (t === 'HITLGate') {
      if (n.prompt)       lines.push('Prompt: ' + String(n.prompt).slice(0, 60));
      if (n.approved != null) lines.push('Approved: ' + n.approved);
      if (n.respondedBy)  lines.push('By: ' + n.respondedBy);
    } else if (t === 'BudgetEvent') {
      if (n.budgetKind) lines.push('Kind: ' + n.budgetKind);
      if (n.limit != null)    lines.push('Limit: ' + n.limit);
      if (n.consumed != null) lines.push('Consumed: ' + n.consumed);
    } else if (t === 'ControlIntervention') {
      if (n.interventionType) lines.push('Type: ' + n.interventionType);
      if (n.reason)           lines.push('Reason: ' + String(n.reason).slice(0, 80));
    } else if (t === 'CallAnnotation') {
      if (n.annotationKind) lines.push('Kind: ' + n.annotationKind);
      if (n.content)        lines.push('Content: ' + String(n.content).slice(0, 80));
    } else if (t === 'ParallelGroup') {
      if (n.groupId)      lines.push('Group: ' + n.groupId);
      if (n.branchCount != null) lines.push('Branches: ' + n.branchCount);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
    } else if (t === 'RAGQuery') {
      if (n.queryText)          lines.push('Query: ' + String(n.queryText).slice(0, 60));
      if (n.retrievedDocCount != null) lines.push('Docs: ' + n.retrievedDocCount);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
    } else if (t === 'NetworkCall') {
      if (n.url)        lines.push('URL: ' + String(n.url).slice(0, 60));
      if (n.method)     lines.push('Method: ' + n.method);
      if (n.statusCode) lines.push('Status: ' + n.statusCode);
      const dur = durationStr(n.startTime, n.endTime);
      if (dur) lines.push('Duration: ' + dur);
    } else {
      let count = 0;
      for (const [k, v] of Object.entries(n)) {
        if (k === 'id' || k === 'node_type' || v == null) continue;
        if (typeof v === 'object') continue;
        lines.push(k + ': ' + String(v).slice(0, 60));
        if (++count >= 4) break;
      }
    }
    return lines.length ? t + '\n' + lines.join('\n') : t;
  }

  function durationStr(startMs, endMs) {
    if (!startMs || !endMs) return null;
    const ms = (endMs - startMs) * (endMs > 1e10 ? 1 : 1000);
    if (ms < 1000) return ms.toFixed(0) + 'ms';
    return (ms / 1000).toFixed(2) + 's';
  }

  // ─── Build Cytoscape elements ──────────────────────────────────────────────
  // edgeFilterFn(srcType, tgtType) -> bool  — optional per-edge predicate
  // groupLayersSet Set<layerId>             — optional per-layer compound groups
  //   (when set, overrides the useGroups boolean)
  function buildElements(kg, activeNodeTypes, activeEdgeTypes, maxNodes, useGroups, nodeStyles, edgeFilterFn, groupLayersSet) {
    const nodeMap = {};
    const nodes   = (kg.nodes || []).slice(0, maxNodes);
    const elements = [];

    // Determine which layers to group
    const activeGroups = groupLayersSet != null ? groupLayersSet
      : (useGroups ? new Set(LAYERS.map(l => l.id)) : new Set());

    // Group parent nodes (compound)
    if (activeGroups.size > 0) {
      const layersSeen = new Set();
      nodes.forEach(n => {
        const ntype = n.node_type || '';
        if (activeNodeTypes && !activeNodeTypes.has(ntype)) return;
        const lid = TYPE_TO_LAYER[ntype];
        if (lid && activeGroups.has(lid)) layersSeen.add(lid);
      });
      LAYERS.forEach(l => {
        if (!layersSeen.has(l.id)) return;
        elements.push({ group:'nodes', data:{
          id: '__layer__' + l.id,
          label: l.label,
          isGroup: true,
        }});
      });
    }

    for (const n of nodes) {
      const nid   = n.id || n.node_type || '?';
      const ntype = n.node_type || '';
      if (activeNodeTypes && !activeNodeTypes.has(ntype)) continue;
      const s = nodeStyles[ntype] || (nodeStyles === NODE_DARK ? NODE_DARK_DEFAULT : NODE_LIGHT_DEFAULT);
      nodeMap[nid] = n;
      const _lid = TYPE_TO_LAYER[ntype];
      const parentId = (_lid && activeGroups.size > 0 && activeGroups.has(_lid)) ? '__layer__' + _lid : undefined;
      const el = { group:'nodes', data:{
        id: nid, label: shortLabel(n), node_type: ntype,
        bg: s.bg, fg: s.fg, border: s.border, shape: s.shape, size: s.size,
      }};
      if (parentId) el.data.parent = parentId;
      elements.push(el);
    }

    const visibleIds = new Set(elements.filter(e => !e.data.isGroup).map(e => e.data.id));
    let edgeIdx = 0;
    for (const e of (kg.edges || [])) {
      const src = e.source || e.from || e.from_id || '';
      const tgt = e.target || e.to   || e.to_id   || '';
      if (!src || !tgt || !visibleIds.has(src) || !visibleIds.has(tgt)) continue;
      const rel = e.relation || e.type || e.label || e.edge_type || '';
      if (activeEdgeTypes && activeEdgeTypes.size > 0 && !activeEdgeTypes.has(rel)) continue;
      // Per-edge filter (e.g. inner/outer layer edges from KGComposer)
      if (edgeFilterFn) {
        const srcType = (nodeMap[src] || {}).node_type || '';
        const tgtType = (nodeMap[tgt] || {}).node_type || '';
        if (!edgeFilterFn(srcType, tgtType)) continue;
      }
      elements.push({ group:'edges', data:{
        id: 'e' + edgeIdx++, source: src, target: tgt,
        label: rel.length > 14 ? rel.slice(0,13) + '\u2026' : rel,
      }});
    }

    return { elements, nodeMap };
  }

  // ─── Cytoscape stylesheet (theme-aware) ────────────────────────────────────
  function buildCyStyle(theme) {
    const isDark     = theme === 'dark';
    const edgeColor  = isDark ? EDGE_COLOR_DARK : EDGE_COLOR_LIGHT;
    const edgeLbl    = isDark ? '#64748b' : '#94a3b8';
    const dimOpacity = 0.12;
    const groupBg    = isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)';
    const groupBorder = isDark ? '#334155' : '#e2e8f0';

    return [
      { selector:'node', style:{
          'background-color':  'data(bg)',
          'label':             'data(label)',
          'color':             'data(fg)',
          'font-size':         10,
          'text-valign':       'center',
          'text-halign':       'center',
          'text-wrap':         'wrap',
          'text-max-width':    'data(size)',
          'width':             'data(size)',
          'height':            'data(size)',
          'shape':             'data(shape)',
          'border-width':      1.5,
          'border-color':      'data(border)',
          'transition-property': 'opacity, border-width',
          'transition-duration': '0.15s',
      }},
      { selector:'node:selected', style:{
          'border-color': '#f0abfc', 'border-width': 3,
      }},
      { selector:'node.dimmed', style:{ 'opacity': dimOpacity }},
      { selector:'node.highlighted', style:{
          'border-color': '#f0abfc', 'border-width': 2.5,
      }},
      // Compound group nodes
      { selector:'node[?isGroup]', style:{
          'background-color':   groupBg,
          'border-color':       groupBorder,
          'border-width':       1,
          'border-style':       'dashed',
          'label':              'data(label)',
          'font-size':          10,
          'text-valign':        'top',
          'text-halign':        'center',
          'color':              edgeLbl,
          'padding':            '12px',
          'shape':              'roundrectangle',
      }},
      { selector:'edge', style:{
          'line-color':              edgeColor,
          'target-arrow-color':      edgeColor,
          'target-arrow-shape':      'triangle',
          'curve-style':             'bezier',
          'width':                   1.2,
          'label':                   'data(label)',
          'font-size':               8,
          'color':                   edgeLbl,
          'text-rotation':           'autorotate',
          'text-background-color':   isDark ? '#0f172a' : '#f8fafc',
          'text-background-opacity': 0.7,
          'text-background-padding': '1px',
          'opacity':                 0.7,
      }},
      { selector:'edge:selected', style:{ 'opacity':1, 'width':2.5 }},
      { selector:'edge.dimmed',   style:{ 'opacity': 0.06 }},
    ];
  }

  // ─── Rich detail panel HTML ────────────────────────────────────────────────

  function prop(k, v) {
    if (v == null || v === '') return '';
    return '<div class="kg-prop"><span class="kg-prop-key">' + esc(k) + '</span>'
         + '<span class="kg-prop-val">' + esc(String(v)) + '</span></div>';
  }

  // Serialize any value (string, array, object) to a display string.
  // Returns null when the value is meaningfully empty (null, '', [], {}).
  function fieldVal(v) {
    if (v == null) return null;
    if (typeof v === 'string') return v.trim() || null;
    if (Array.isArray(v))      return v.length ? JSON.stringify(v, null, 2) : null;
    if (typeof v === 'object') {
      try {
        const s = JSON.stringify(v, null, 2);
        return (s === '{}' || s === '[]') ? null : s;
      } catch (_) { return null; }
    }
    const s = String(v);
    return s || null;
  }

  // Collapsible section. Accepts raw value of any type (array/object → JSON).
  function collapsible(id, label, rawVal, open) {
    const content = fieldVal(rawVal);
    if (!content) return '';
    const cls = open ? ' open' : '';
    return '<div class="kg-content-section">'
      + '<button class="kg-content-toggle' + cls + '" onclick="this.classList.toggle(\'open\')">'
      + '<span class="kg-chevron">&#9658;</span> ' + esc(label) + '</button>'
      + '<div class="kg-content-body"><pre class="kg-content-pre">' + esc(content) + '</pre></div>'
      + '</div>';
  }

  function tokenBar(prompt, compl) {
    if (!prompt && !compl) return '';
    const total = (prompt || 0) + (compl || 0);
    const pp = total > 0 ? Math.round((prompt || 0) / total * 100) : 50;
    const cp = 100 - pp;
    return '<div class="kg-token-bar-wrap">'
      + '<div class="kg-token-label">Tokens</div>'
      + '<div class="kg-token-bar">'
      + '<div class="kg-token-prompt" style="width:' + pp + '%"></div>'
      + '<div class="kg-token-compl"  style="width:' + cp + '%"></div>'
      + '</div>'
      + '<div class="kg-token-numbers"><span>prompt: ' + (prompt||0) + '</span><span>completion: ' + (compl||0) + '</span></div>'
      + '</div>';
  }

  function sectionDiv(label) {
    return '<div class="kg-section-div">' + esc(label) + '</div>';
  }

  // Show all fields in rawNode NOT already listed in shownKeys.
  // Small scalars → prop(); large/blob fields → collapsible().
  const BLOB_KEYS = new Set([
    'content','prompt','completion','inputContent','outputContent',
    'toolArguments','toolOutput','finalResponse','inputQuery',
  ]);
  function allProps(rawNode, shownKeys) {
    const skip = new Set(['node_type', 'id', ...shownKeys]);
    let scalarHtml = '';
    const blobs = [];
    for (const [k, v] of Object.entries(rawNode)) {
      if (skip.has(k) || v == null) continue;
      if (BLOB_KEYS.has(k)) {
        const fv = fieldVal(v);
        if (fv) blobs.push([k, fv]);
        continue;
      }
      if (typeof v === 'object') {
        try {
          const fv = fieldVal(v);
          if (fv) scalarHtml += prop(k, fv.length > 100 ? fv.slice(0, 100) + '\u2026' : fv);
        } catch (_) {}
      } else {
        const s = String(v);
        if (s) scalarHtml += prop(k, s.length > 160 ? s.slice(0, 160) + '\u2026' : s);
      }
    }
    let html = scalarHtml;
    for (const [k, fv] of blobs) {
      html += collapsible(k, k, fv, false);
    }
    return html ? sectionDiv('All fields') + html : '';
  }

  function formatDetail(rawNode) {
    if (!rawNode) return '';
    const t = rawNode.node_type || '';

    if (t === 'LLMCall') {
      const shown = new Set([
        'modelName','llmName','status','finishReason','startTime','endTime',
        'callId','agentId','promptTokenCount','completionTokenCount',
        'prompt','completion',
      ]);
      return sectionDiv('LLM Call')
        + prop('Model',      rawNode.modelName || rawNode.llmName)
        + prop('Agent',      rawNode.agentId)
        + prop('Status',     rawNode.status)
        + prop('Finish',     rawNode.finishReason)
        + prop('Duration',   durationStr(rawNode.startTime, rawNode.endTime))
        + prop('Call ID',    rawNode.callId)
        + tokenBar(rawNode.promptTokenCount, rawNode.completionTokenCount)
        + collapsible('prompt', 'Prompt',     rawNode.prompt,     false)
        + collapsible('compl',  'Completion', rawNode.completion, true)
        + allProps(rawNode, shown);
    }

    if (t === 'State') {
      const shown = new Set([
        'semanticType','deltaType','stateNodeId','contentHash',
        'sourceCallId','sessionId','content',
      ]);
      return sectionDiv('State')
        + prop('Type',       rawNode.semanticType)
        + prop('Delta',      rawNode.deltaType)
        + prop('Session',    rawNode.sessionId)
        + prop('Source call',rawNode.sourceCallId)
        + prop('Node ID',    rawNode.stateNodeId)
        + prop('Hash',       rawNode.contentHash ? rawNode.contentHash.slice(0,12) + '\u2026' : null)
        + collapsible('content', 'Content', rawNode.content, true)
        + allProps(rawNode, shown);
    }

    if (t === 'ToolCall') {
      const shown = new Set([
        'toolName','status','startTime','endTime','callId','agentId',
        'toolArguments','toolOutput',
      ]);
      return sectionDiv('Tool Call')
        + prop('Tool',     rawNode.toolName)
        + prop('Agent',    rawNode.agentId)
        + prop('Status',   rawNode.status)
        + prop('Duration', durationStr(rawNode.startTime, rawNode.endTime))
        + prop('Call ID',  rawNode.callId)
        + collapsible('args',   'Arguments', rawNode.toolArguments, true)
        + collapsible('output', 'Output',    rawNode.toolOutput,    false)
        + allProps(rawNode, shown);
    }

    if (t === 'AgentCall') {
      const shown = new Set([
        'agentName','agentId','agentType','status','startTime','endTime',
        'callId','inputContent','outputContent',
      ]);
      return sectionDiv('Agent Call')
        + prop('Agent',    rawNode.agentName || rawNode.agentId)
        + prop('Type',     rawNode.agentType)
        + prop('Status',   rawNode.status)
        + prop('Duration', durationStr(rawNode.startTime, rawNode.endTime))
        + prop('Call ID',  rawNode.callId)
        + collapsible('in',  'Input',  rawNode.inputContent,  false)
        + collapsible('out', 'Output', rawNode.outputContent, true)
        + allProps(rawNode, shown);
    }

    if (t === 'Transition') {
      const shown = new Set([
        'actionType','appliedOperator','edgeType','fromState','toState',
        'realizesCallId','transitionTimestamp',
      ]);
      return sectionDiv('Transition')
        + prop('Action',   rawNode.actionType)
        + prop('Operator', rawNode.appliedOperator)
        + prop('Type',     rawNode.edgeType)
        + prop('From',     rawNode.fromState)
        + prop('To',       rawNode.toState)
        + prop('Realizes', rawNode.realizesCallId)
        + prop('At', rawNode.transitionTimestamp
            ? new Date(rawNode.transitionTimestamp * 1000).toISOString() : null)
        + allProps(rawNode, shown);
    }

    if (t === 'Session') {
      const shown = new Set([
        'sessionId','runId','startTime','endTime','inputQuery','finalResponse',
      ]);
      return sectionDiv('Session')
        + prop('Session ID', rawNode.sessionId)
        + prop('Run ID',     rawNode.runId)
        + prop('Duration',   durationStr(rawNode.startTime, rawNode.endTime))
        + collapsible('iq', 'Input Query',    rawNode.inputQuery,    true)
        + collapsible('fr', 'Final Response', rawNode.finalResponse, false)
        + allProps(rawNode, shown);
    }

    if (t === 'MASCall') {
      const shown = new Set([
        'masName','masType','agentId','status','startTime','endTime','callId',
        'inputContent','outputContent',
      ]);
      return sectionDiv('MAS Call')
        + prop('MAS',      rawNode.masName)
        + prop('Type',     rawNode.masType)
        + prop('Agent',    rawNode.agentId)
        + prop('Status',   rawNode.status)
        + prop('Duration', durationStr(rawNode.startTime, rawNode.endTime))
        + prop('Call ID',  rawNode.callId)
        + collapsible('in',  'Input',  rawNode.inputContent,  false)
        + collapsible('out', 'Output', rawNode.outputContent, true)
        + allProps(rawNode, shown);
    }

    if (t === 'Tool' || t === 'LLM' || t === 'Skill') {
      const shown = new Set(['name','masUri','block','callCount']);
      return sectionDiv(t)
        + prop('Name',   rawNode.name)
        + prop('URI',    rawNode.masUri)
        + prop('Block',  rawNode.block)
        + prop('Calls',  rawNode.callCount)
        + allProps(rawNode, shown);
    }

    // Generic fallback — show everything
    const SKIP = new Set(['node_type','id']);
    let html = sectionDiv(t);
    const blobs = [];
    for (const [k, v] of Object.entries(rawNode)) {
      if (SKIP.has(k) || v == null) continue;
      if (BLOB_KEYS.has(k)) { blobs.push([k, v]); continue; }
      if (typeof v === 'object') {
        const fv = fieldVal(v);
        if (fv) html += prop(k, fv.length > 100 ? fv.slice(0,100) + '\u2026' : fv);
      } else {
        const s = String(v);
        if (s) html += prop(k, s.length > 160 ? s.slice(0,160) + '\u2026' : s);
      }
    }
    for (const [k, v] of blobs) {
      html += collapsible(k, k, v, false);
    }
    return html;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // KGGraph — bare graph component (no filter panel)
  //
  // Usage:
  //   const g = new KGGraph(el, kg, { theme:'dark', layout:'dagre-tb', title:'' });
  //   g.setFilter(nodeTypeSet, edgeTypeSet);   g.setTheme('light');   g.destroy();
  //
  // Exposes `toolbarLeftEl` so a wrapper can inject extra toolbar buttons.
  // ═══════════════════════════════════════════════════════════════════════════
  function KGGraph(container, kg, opts) {
    opts = Object.assign({ theme:'dark', layout:'dagre-tb', maxNodes:300, title:'' }, opts || {});
    this._container = container;
    this._kg        = kg || { nodes:[], edges:[] };
    this._opts      = opts;
    this._cy        = null;
    this._nodeMap   = {};
    this._activeNodeTypes = null;
    this._activeEdgeTypes = null;
    this._currentLayout   = opts.layout;
    this._useGroups       = false;
    this._focusedId       = null;
    this._theme           = opts.theme;
    this._currentNodeId   = null;
    this._edgeFilter      = null;   // function(srcType, tgtType) -> bool
    this._groupLayers     = null;   // Set<layerId> for per-layer compound groups

    container.classList.add('kg-widget', 'kg-graph');
    this._applyThemeClass();
    this._buildDOM();
    this._render();
    this._bindEvents();
  }

  KGGraph.prototype._applyThemeClass = function () {
    if (this._theme === 'light') {
      this._container.classList.add('kg-light');
    } else {
      this._container.classList.remove('kg-light');
    }
  };

  KGGraph.prototype._nodeStyles = function () {
    return this._theme === 'light' ? NODE_LIGHT : NODE_DARK;
  };

  KGGraph.prototype._buildDOM = function () {
    const titleHtml = this._opts.title
      ? '<span class="kg-title">' + esc(this._opts.title) + '</span>' : '';

    this._container.innerHTML =
      '<div class="kg-toolbar">'
      + '<div class="kg-toolbar-left">'
      + titleHtml
      + '</div>'
      + '<div class="kg-toolbar-right">'
      + '<button class="kg-btn kg-group-toggle" title="Group nodes by semantic layer">Group</button>'
      + '<button class="kg-btn kg-focus-reset kg-btn-icon" title="Reset focus" style="display:none">\u00d7 Focus</button>'
      + '<select class="kg-select kg-layout-select" title="Layout">'
      + '<option value="dagre-tb">Dagre \u2193</option>'
      + '<option value="dagre-lr">Dagre \u2192</option>'
      + '<option value="breadthfirst">BFS</option>'
      + '<option value="cose-bilkent">CoSE</option>'
      + '</select>'
      + '<button class="kg-btn kg-btn-icon kg-fit-btn" title="Fit">&#x22a1;</button>'
      + '<button class="kg-btn kg-btn-icon kg-theme-toggle" title="Toggle theme">\u263d</button>'
      + '<button class="kg-btn kg-btn-icon kg-export-btn" title="Export SVG">\u2193</button>'
      + '</div>'
      + '</div>'
      + '<div class="kg-graph-body">'
      + '<div class="kg-cy-container"></div>'
      + '<div class="kg-detail kg-detail-hidden">'
      + '<div class="kg-detail-header">'
      + '<span class="kg-detail-type-badge"></span>'
      + '<span class="kg-detail-label"></span>'
      + '<button class="kg-detail-close">\u00d7</button>'
      + '</div>'
      + '<div class="kg-detail-actions">'
      + '<button class="kg-detail-action kg-action-focus">Focus</button>'
      + '<button class="kg-detail-action kg-action-neighbors">Neighbors</button>'
      + '</div>'
      + '<div class="kg-detail-body"></div>'
      + '</div>'
      + '</div>';

    // Exposed for wrapper components to inject extra toolbar buttons
    this.toolbarLeftEl  = this._container.querySelector('.kg-toolbar-left');
    this._cyContainerEl = this._container.querySelector('.kg-cy-container');
    this._detailEl      = this._container.querySelector('.kg-detail');
    this._detailBadge   = this._container.querySelector('.kg-detail-type-badge');
    this._detailLabel   = this._container.querySelector('.kg-detail-label');
    this._detailBody    = this._container.querySelector('.kg-detail-body');
    this._layoutSelect  = this._container.querySelector('.kg-layout-select');
    this._layoutSelect.value = this._currentLayout;

    // Floating hover tooltip (appended to body, position:fixed)
    this._tooltipEl = document.createElement('div');
    this._tooltipEl.className = 'kg-tooltip';
    document.body.appendChild(this._tooltipEl);
  };

  KGGraph.prototype._render = function (preserveVp) {
    const { elements, nodeMap } = buildElements(
      this._kg,
      this._activeNodeTypes,
      this._activeEdgeTypes,
      this._opts.maxNodes,
      this._useGroups,
      this._nodeStyles(),
      this._edgeFilter  || null,
      this._groupLayers || null,
    );
    this._nodeMap = nodeMap;

    const layoutConf = LAYOUTS[this._currentLayout] || LAYOUTS['dagre-tb'];
    const self = this;

    if (this._cy) {
      this._cy.destroy();
      this._cy = null;
    }

    if (!window.cytoscape) {
      this._cyContainerEl.innerHTML = '<div class="kg-error">cytoscape.js not loaded.</div>';
      return;
    }

    this._cy = window.cytoscape({
      container:        this._cyContainerEl,
      elements:         elements,
      style:            buildCyStyle(this._theme),
      layout:           layoutConf,
      wheelSensitivity: 0.2,
      minZoom: 0.1, maxZoom: 4,
    });

    const cy = this._cy;

    cy.on('tap', 'node', function (evt) {
      const d = evt.target.data();
      if (d.isGroup) return;
      self._showDetail(d, self._nodeMap[d.id]);
    });

    cy.on('tap', function (evt) {
      if (evt.target === cy) {
        self._detailEl.classList.add('kg-detail-hidden');
      }
    });

    cy.on('mouseover', 'node', function (evt) {
      const d = evt.target.data();
      if (d.isGroup) return;
      const tip = shortTip(self._nodeMap[d.id] || d);
      if (!tip) return;
      self._tooltipEl.textContent = tip;
      self._tooltipEl.style.display = 'block';
      if (self._lastMouseX != null) self._positionTooltip(self._lastMouseX, self._lastMouseY);
    });
    cy.on('mouseout', 'node', function () {
      self._tooltipEl.style.display = 'none';
    });

    cy.on('layoutstop', function () { cy.fit(undefined, 24); });
  };

  KGGraph.prototype._showDetail = function (data, rawNode) {
    this._currentNodeId = data.id;
    const ntype = data.node_type || '';
    const styles = this._nodeStyles();
    const s = styles[ntype] || NODE_DARK_DEFAULT;

    this._detailBadge.textContent = ntype || '?';
    this._detailBadge.style.cssText =
      'background:' + s.bg + ';color:' + s.fg + ';border-color:' + s.border;
    this._detailLabel.textContent = data.label || data.id || '';
    this._detailBody.innerHTML = formatDetail(rawNode);
    this._detailEl.classList.remove('kg-detail-hidden');
  };

  KGGraph.prototype._highlightNeighborhood = function (nodeId, mode) {
    const cy = this._cy;
    if (!cy) return;
    const node = cy.getElementById(nodeId);
    if (!node.length) return;
    cy.elements().removeClass('highlighted dimmed');
    const neighborhood = node.closedNeighborhood();
    if (mode === 'focus') {
      cy.elements().not(neighborhood).addClass('dimmed');
      neighborhood.addClass('highlighted');
    } else {
      neighborhood.addClass('highlighted');
    }
    this._focusedId = nodeId;
    this._container.querySelector('.kg-focus-reset').style.display = '';
  };

  KGGraph.prototype._resetHighlight = function () {
    if (this._cy) this._cy.elements().removeClass('highlighted dimmed');
    this._focusedId = null;
    this._container.querySelector('.kg-focus-reset').style.display = 'none';
  };

  KGGraph.prototype._exportSVG = function () {
    if (!this._cy) return;
    let svg;
    try {
      svg = this._cy.svg({ full:true, bg: this._theme === 'dark' ? '#0f172a' : '#f8fafc' });
    } catch (_) {
      const png = this._cy.png({ full:true });
      const a = document.createElement('a');
      a.href = png; a.download = 'kg.png'; a.click();
      return;
    }
    const blob = new Blob([svg], { type:'image/svg+xml' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'kg.svg'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };

  KGGraph.prototype._positionTooltip = function (cx, cy) {
    const el = this._tooltipEl;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const tw = el.offsetWidth  || 220;
    const th = el.offsetHeight || 60;
    const x  = (cx + 18 + tw > vw) ? cx - tw - 10 : cx + 18;
    const y  = (cy + 18 + th > vh) ? cy - th - 10 : cy + 18;
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
  };

  KGGraph.prototype._bindEvents = function () {
    const self = this;

    // Mouse tracking for tooltip positioning
    this._lastMouseX = null;
    this._lastMouseY = null;
    this._cyContainerEl.addEventListener('mousemove', function (e) {
      self._lastMouseX = e.clientX;
      self._lastMouseY = e.clientY;
      if (self._tooltipEl.style.display !== 'none') {
        self._positionTooltip(e.clientX, e.clientY);
      }
    }, { passive: true });
    this._cyContainerEl.addEventListener('mouseleave', function () {
      self._tooltipEl.style.display = 'none';
    });

    // Layout select
    this._layoutSelect.addEventListener('change', function () {
      self._currentLayout = this.value;
      if (self._cy) {
        self._cy.layout(LAYOUTS[self._currentLayout] || LAYOUTS['dagre-tb']).run();
      }
    });

    // Fit
    this._container.querySelector('.kg-fit-btn').addEventListener('click', function () {
      if (self._cy) self._cy.fit(undefined, 24);
    });

    // Theme toggle
    this._container.querySelector('.kg-theme-toggle').addEventListener('click', function () {
      self.setTheme(self._theme === 'dark' ? 'light' : 'dark');
    });

    // Group toggle
    this._container.querySelector('.kg-group-toggle').addEventListener('click', function () {
      self.setGroups(!self._useGroups);
      this.classList.toggle('active', self._useGroups);
    });

    // Focus reset
    this._container.querySelector('.kg-focus-reset').addEventListener('click', function () {
      self._resetHighlight();
    });

    // SVG export
    this._container.querySelector('.kg-export-btn').addEventListener('click', function () {
      self._exportSVG();
    });

    // Detail panel actions
    this._container.querySelector('.kg-action-focus').addEventListener('click', function () {
      if (self._currentNodeId) {
        const isActive = this.classList.contains('active');
        self._container.querySelectorAll('.kg-detail-action').forEach(a => a.classList.remove('active'));
        if (isActive) { self._resetHighlight(); }
        else { this.classList.add('active'); self._highlightNeighborhood(self._currentNodeId, 'focus'); }
      }
    });

    this._container.querySelector('.kg-action-neighbors').addEventListener('click', function () {
      if (self._currentNodeId) {
        const isActive = this.classList.contains('active');
        self._container.querySelectorAll('.kg-detail-action').forEach(a => a.classList.remove('active'));
        if (isActive) { self._resetHighlight(); }
        else { this.classList.add('active'); self._highlightNeighborhood(self._currentNodeId, 'neighbors'); }
      }
    });

    // Detail panel close
    this._container.querySelector('.kg-detail-close').addEventListener('click', function () {
      self._detailEl.classList.add('kg-detail-hidden');
      self._resetHighlight();
      self._container.querySelectorAll('.kg-detail-action').forEach(a => a.classList.remove('active'));
    });
  };

  // ─── KGGraph public API ────────────────────────────────────────────────────
  KGGraph.prototype.setData = function (kg) {
    this._kg = kg || { nodes:[], edges:[] };
    this._render();
  };

  KGGraph.prototype.setFilter = function (nodeTypes, edgeTypes) {
    this._activeNodeTypes = nodeTypes || null;
    this._activeEdgeTypes = edgeTypes || null;
    this._render();
  };

  KGGraph.prototype.setTheme = function (theme) {
    this._theme = theme;
    this._applyThemeClass();
    if (this._cy) {
      this._cy.style(buildCyStyle(theme));
    }
    if (this._cyContainerEl) {
      this._cyContainerEl.style.background = theme === 'dark' ? '#0f172a' : '#f8fafc';
    }
  };

  KGGraph.prototype.setLayout = function (name) {
    this._currentLayout = name;
    if (this._layoutSelect) this._layoutSelect.value = name;
    if (this._cy) {
      this._cy.layout(LAYOUTS[name] || LAYOUTS['dagre-tb']).run();
    }
  };

  KGGraph.prototype.setGroups = function (bool) {
    this._useGroups = bool;
    this._render();
  };

  /**
   * setEdgeFilter(fn) — install a per-edge predicate.
   * fn(srcNodeType: string, tgtNodeType: string) -> boolean
   * Passing null removes the filter.
   */
  KGGraph.prototype.setEdgeFilter = function (fn) {
    this._edgeFilter = fn || null;
    this._render();
  };

  /**
   * setGroupLayers(layerSet) — enable compound grouping for a specific set of
   * layer IDs (e.g. new Set(['call', 'memory'])). Passing null falls back to
   * the global useGroups toggle.
   */
  KGGraph.prototype.setGroupLayers = function (layerSet) {
    this._groupLayers = layerSet || null;
    this._render();
  };

  KGGraph.prototype.getNodeCount = function () {
    return this._cy ? this._cy.nodes(':visible').length : 0;
  };

  KGGraph.prototype.destroy = function () {
    if (this._cy) { this._cy.destroy(); this._cy = null; }
    if (this._tooltipEl && this._tooltipEl.parentNode) {
      this._tooltipEl.parentNode.removeChild(this._tooltipEl);
      this._tooltipEl = null;
    }
    this._container.innerHTML = '';
    this._container.classList.remove('kg-widget', 'kg-graph', 'kg-light');
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // KGWidget — filter panel + KGGraph
  //
  // Usage:
  //   const w = new KGWidget(el, kg, {
  //     theme: 'dark', layout: 'dagre-tb', title: '',
  //     panelMode: 'open',        // 'open' | 'closed'
  //     filterStyle: 'flat',      // 'flat' (original) | 'layered' (v2 groups)
  //   });
  //   w.setData(kg);   w.setTheme('light');   w.openPanel();   w.destroy();
  // ═══════════════════════════════════════════════════════════════════════════
  function KGWidget(container, kg, opts) {
    opts = Object.assign({
      theme: 'dark', layout: 'dagre-tb', maxNodes: 300,
      title: '', panelMode: 'open', filterStyle: 'flat',
    }, opts || {});
    this._container   = container;
    this._kg          = kg || { nodes:[], edges:[] };
    this._opts        = opts;
    this._theme       = opts.theme;
    this._filterStyle = opts.filterStyle;

    container.classList.add('kg-widget');
    this._applyThemeClass();
    this._buildDOM();
    this._populateFilters();
    this._updateActiveFilters();
    this._bindFilterEvents();
  }

  KGWidget.prototype._applyThemeClass = function () {
    if (this._theme === 'light') {
      this._container.classList.add('kg-light');
    } else {
      this._container.classList.remove('kg-light');
    }
  };

  KGWidget.prototype._nodeStyles = function () {
    return this._theme === 'light' ? NODE_LIGHT : NODE_DARK;
  };

  // ─── Build outer DOM: panel + graph-wrapper ────────────────────────────────
  KGWidget.prototype._buildDOM = function () {
    const panelOpen = this._opts.panelMode !== 'closed';

    // Build outer skeleton: panel + graph-wrapper side-by-side
    this._container.innerHTML =
      '<div class="kg-body">'
      + '<div class="kg-panel' + (panelOpen ? '' : ' kg-panel-hidden') + '">'
      + '<div class="kg-panel-content"></div>'
      + '<div class="kg-stats-bar"></div>'
      + '</div>'
      + '<div class="kg-graph-wrapper"></div>'
      + '</div>';

    this._panelEl        = this._container.querySelector('.kg-panel');
    this._panelContentEl = this._container.querySelector('.kg-panel-content');
    this._statsEl        = this._container.querySelector('.kg-stats-bar');
    const wrapperEl      = this._container.querySelector('.kg-graph-wrapper');

    // Create KGGraph inside the wrapper
    this._graph = new KGGraph(wrapperEl, this._kg, {
      theme:    this._opts.theme,
      layout:   this._opts.layout,
      maxNodes: this._opts.maxNodes,
      title:    this._opts.title,
    });

    // Inject panel-toggle button into KGGraph's toolbar-left hook
    const self    = this;
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'kg-btn kg-panel-toggle kg-btn-icon';
    toggleBtn.title     = 'Toggle filter panel';
    toggleBtn.innerHTML = '&#9776;';
    toggleBtn.addEventListener('click', function () {
      self._panelEl.classList.toggle('kg-panel-hidden');
    });
    this._graph.toolbarLeftEl.insertBefore(toggleBtn, this._graph.toolbarLeftEl.firstChild);
  };

  // ─── Populate the filter panel (flat or layered) ───────────────────────────
  KGWidget.prototype._populateFilters = function () {
    const kg         = this._kg;
    const nodeStyles = this._nodeStyles();

    // Count types present in the data
    const typeCounts = {};
    (kg.nodes || []).forEach(n => { typeCounts[n.node_type] = (typeCounts[n.node_type] || 0) + 1; });

    // Edge types in data
    const edgeTypes = [...new Set((kg.edges || [])
      .map(e => e.relation || e.type || e.label || e.edge_type || '')
      .filter(Boolean))].sort();

    if (this._filterStyle === 'flat') {
      this._buildFlatPanel(typeCounts, edgeTypes, nodeStyles);
    } else {
      this._buildLayeredPanel(typeCounts, edgeTypes, nodeStyles);
    }
  };

  // ─── Flat panel: original style ───────────────────────────────────────────
  // Node types listed flat (ordered by layers), then edge types, then stats bar.
  KGWidget.prototype._buildFlatPanel = function (typeCounts, edgeTypes, nodeStyles) {
    // Collect node types in layer order, only those present in data
    const nodeTypes = [];
    LAYERS.forEach(l => l.types.forEach(t => { if (typeCounts[t]) nodeTypes.push(t); }));

    let html =
      '<div class="kg-panel-section">'
      + '<div class="kg-panel-section-hdr">Node types'
      + '<span class="kg-check-all" data-target="node">all</span>'
      + '<span class="kg-check-none" data-target="node">none</span>'
      + '</div>'
      + '<div class="kg-node-type-list">'
      + nodeTypes.map(t => {
          const s = nodeStyles[t] || NODE_DARK_DEFAULT;
          return '<label class="kg-filter-row">'
            + '<input type="checkbox" class="kg-node-cb" value="' + t + '" checked>'
            + '<span class="kg-type-dot" style="background:' + s.bg + ';color:' + s.fg + ';border-color:' + s.border + '">'
            + t + ' <small style="opacity:0.7">(' + (typeCounts[t] || 0) + ')</small></span>'
            + '</label>';
        }).join('')
      + '</div>'
      + '</div>'
      + '<div class="kg-panel-section">'
      + '<div class="kg-panel-section-hdr">Edge types'
      + '<span class="kg-check-all" data-target="edge">all</span>'
      + '<span class="kg-check-none" data-target="edge">none</span>'
      + '</div>'
      + '<div class="kg-edge-type-list">'
      + (edgeTypes.length
          ? edgeTypes.map(t => '<label class="kg-filter-row">'
              + '<input type="checkbox" class="kg-edge-cb" value="' + t + '" checked>'
              + '<span class="kg-type-label">' + esc(t) + '</span></label>').join('')
          : '<span style="padding:4px 8px;font-size:10px;color:var(--kg-muted)">No labelled edges</span>'
        )
      + '</div>'
      + '</div>';

    this._panelContentEl.innerHTML = html;
    this._layerGroupsEl = null;  // not used in flat mode
    this._presetListEl  = null;
    this._schemaListEl  = null;
  };

  // ─── Layered panel: v2 style (tabs + layer groups) ────────────────────────
  KGWidget.prototype._buildLayeredPanel = function (typeCounts, edgeTypes, nodeStyles) {
    // Structure
    this._panelContentEl.innerHTML =
      '<div class="kg-panel-tabs">'
      + '<button class="kg-panel-tab active" data-tab="filters">Filters</button>'
      + '<button class="kg-panel-tab" data-tab="presets">Presets</button>'
      + '<button class="kg-panel-tab" data-tab="schema">Schema</button>'
      + '</div>'
      + '<div class="kg-panel-body">'
      + '<div class="kg-tab-pane active" data-pane="filters">'
      + '<div class="kg-layer-groups"></div>'
      + '<div class="kg-panel-section">'
      + '<div class="kg-panel-section-hdr">Edge types'
      + '<span class="kg-check-all" data-target="edge">all</span>'
      + '<span class="kg-check-none" data-target="edge">none</span>'
      + '</div>'
      + '<div class="kg-edge-type-list"></div>'
      + '</div>'
      + '</div>'
      + '<div class="kg-tab-pane" data-pane="presets"><div class="kg-preset-list"></div></div>'
      + '<div class="kg-tab-pane" data-pane="schema"><div class="kg-schema-list"></div></div>'
      + '</div>';

    this._layerGroupsEl = this._panelContentEl.querySelector('.kg-layer-groups');
    this._presetListEl  = this._panelContentEl.querySelector('.kg-preset-list');
    this._schemaListEl  = this._panelContentEl.querySelector('.kg-schema-list');
    const edgeListEl    = this._panelContentEl.querySelector('.kg-edge-type-list');

    // Layer groups with per-layer node type checkboxes
    let layerHtml = '';
    LAYERS.forEach(l => {
      const present = l.types.filter(t => typeCounts[t]);
      if (!present.length) return;
      const total = present.reduce((s, t) => s + (typeCounts[t] || 0), 0);
      layerHtml += '<div class="kg-layer-group" data-layer="' + l.id + '">'
        + '<div class="kg-layer-header">'
        + '<span class="kg-layer-chevron">&#9660;</span>'
        + '<span class="kg-layer-icon">' + l.icon + '</span>'
        + '<span>' + l.label + '</span>'
        + '<span class="kg-layer-count">' + total + '</span>'
        + '<span class="kg-check-all" data-target="node" data-layer="' + l.id + '">all</span>'
        + '<span class="kg-check-none" data-target="node" data-layer="' + l.id + '">none</span>'
        + '</div>'
        + '<div class="kg-layer-items">'
        + present.map(t => {
            const s = nodeStyles[t] || NODE_DARK_DEFAULT;
            return '<label class="kg-filter-row">'
              + '<input type="checkbox" class="kg-node-cb" value="' + t + '" checked>'
              + '<span class="kg-type-dot" style="background:' + s.bg + ';color:' + s.fg + ';border-color:' + s.border + '">'
              + t + ' <small style="opacity:0.7">(' + (typeCounts[t] || 0) + ')</small></span>'
              + '</label>';
          }).join('')
        + '</div>'
        + '</div>';
    });
    this._layerGroupsEl.innerHTML = layerHtml;

    // Edge types
    edgeListEl.innerHTML = edgeTypes.length
      ? edgeTypes.map(t => '<label class="kg-filter-row">'
          + '<input type="checkbox" class="kg-edge-cb" value="' + t + '" checked>'
          + '<span class="kg-type-label">' + esc(t) + '</span></label>').join('')
      : '<span style="padding:4px 8px;font-size:10px;color:var(--kg-muted)">No labelled edges</span>';

    // Presets tab
    this._presetListEl.innerHTML = PRESETS.map(p =>
      '<button class="kg-preset-btn" data-preset="' + p.id + '">'
      + '<div>' + esc(p.label) + '</div>'
      + '<div class="kg-preset-desc">' + esc(p.desc) + '</div>'
      + '</button>'
    ).join('');

    // Schema tab
    this._schemaListEl.innerHTML = Object.entries(SCHEMA).map(([t, s]) => {
      const style = nodeStyles[t] || NODE_DARK_DEFAULT;
      return '<div class="kg-schema-type">'
        + '<div class="kg-schema-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
        + '<span class="kg-type-dot" style="background:' + style.bg + ';color:' + style.fg + ';border-color:' + style.border + '">' + t + '</span>'
        + '<span style="margin-left:4px;font-size:10px;color:var(--kg-muted)">' + esc(s.desc) + '</span>'
        + '</div>'
        + '<div class="kg-schema-fields">'
        + s.fields.map(f => '<div class="kg-schema-field"><span>' + esc(f) + '</span></div>').join('')
        + '</div>'
        + '</div>';
    }).join('');

    // Bind tab switching
    const self = this;
    this._panelContentEl.querySelectorAll('.kg-panel-tab').forEach(tab => {
      tab.addEventListener('click', function () {
        self._panelContentEl.querySelectorAll('.kg-panel-tab').forEach(t => t.classList.remove('active'));
        self._panelContentEl.querySelectorAll('.kg-tab-pane').forEach(p => p.classList.remove('active'));
        this.classList.add('active');
        const pane = self._panelContentEl.querySelector('[data-pane="' + this.dataset.tab + '"]');
        if (pane) pane.classList.add('active');
      });
    });
  };

  // ─── Compute active filters from checkboxes → push to graph ───────────────
  KGWidget.prototype._updateActiveFilters = function () {
    const nodeCbs = this._panelContentEl.querySelectorAll('.kg-node-cb');
    const edgeCbs = this._panelContentEl.querySelectorAll('.kg-edge-cb');

    const uncheckedNodes = [...nodeCbs].filter(cb => !cb.checked).map(cb => cb.value);
    const nodeTypes = uncheckedNodes.length === 0 ? null : (() => {
      const all = new Set([...nodeCbs].map(cb => cb.value));
      uncheckedNodes.forEach(v => all.delete(v));
      return all;
    })();

    const checkedEdges = [...edgeCbs].filter(cb => cb.checked).map(cb => cb.value);
    const edgeTypes = (edgeCbs.length === 0 || checkedEdges.length === edgeCbs.length)
      ? null : new Set(checkedEdges);

    this._graph.setFilter(nodeTypes, edgeTypes);
    this._updateStats();
  };

  KGWidget.prototype._updateStats = function () {
    const n = (this._kg.nodes || []).length;
    const e = (this._kg.edges || []).length;
    const vis = this._graph ? this._graph.getNodeCount() : n;
    this._statsEl.textContent = vis + ' / ' + n + ' nodes \u00b7 ' + e + ' edges';
  };

  KGWidget.prototype._applyPreset = function (presetId) {
    const preset = PRESETS.find(p => p.id === presetId);
    if (!preset) return;
    const nodeCbs = this._panelContentEl.querySelectorAll('.kg-node-cb');
    if (preset.nodes === null) {
      nodeCbs.forEach(cb => { cb.checked = true; });
    } else {
      const allowed = new Set(preset.nodes);
      nodeCbs.forEach(cb => { cb.checked = allowed.has(cb.value); });
    }
    this._updateActiveFilters();
  };

  // ─── Bind all filter panel events ─────────────────────────────────────────
  KGWidget.prototype._bindFilterEvents = function () {
    const self = this;

    // Node type checkboxes — any checkbox change triggers filter update
    this._panelContentEl.addEventListener('change', function () {
      self._updateActiveFilters();
    });

    // Layer group collapse (layered style only)
    this._panelContentEl.addEventListener('click', function (evt) {
      const hdr = evt.target.closest('.kg-layer-header');
      if (hdr && !evt.target.closest('.kg-check-all, .kg-check-none')) {
        hdr.closest('.kg-layer-group').classList.toggle('collapsed');
      }
    });

    // Check-all / check-none buttons
    this._panelContentEl.addEventListener('click', function (evt) {
      const btn = evt.target.closest('.kg-check-all, .kg-check-none');
      if (!btn) return;
      evt.stopPropagation();
      const target  = btn.dataset.target;
      const checked = btn.classList.contains('kg-check-all');
      const layerId = btn.dataset.layer;
      if (target === 'node') {
        let cbs;
        if (layerId && self._layerGroupsEl) {
          const grp = self._layerGroupsEl.querySelector('[data-layer="' + layerId + '"]');
          cbs = grp ? grp.querySelectorAll('.kg-node-cb') : [];
        } else {
          cbs = self._panelContentEl.querySelectorAll('.kg-node-cb');
        }
        cbs.forEach(cb => { cb.checked = checked; });
      } else {
        self._panelContentEl.querySelectorAll('.kg-edge-cb').forEach(cb => { cb.checked = checked; });
      }
      self._updateActiveFilters();
    });

    // Preset buttons (layered style only)
    this._panelContentEl.addEventListener('click', function (evt) {
      const btn = evt.target.closest('.kg-preset-btn');
      if (btn) self._applyPreset(btn.dataset.preset);
    });
  };

  // ─── KGWidget public API ───────────────────────────────────────────────────
  KGWidget.prototype.setData = function (kg) {
    this._kg = kg || { nodes:[], edges:[] };
    this._graph.setData(this._kg);
    this._populateFilters();
    this._updateActiveFilters();
    this._bindFilterEvents();
  };

  KGWidget.prototype.setTheme = function (theme) {
    this._theme = theme;
    this._applyThemeClass();
    this._graph.setTheme(theme);
    this._populateFilters();
    this._updateActiveFilters();
  };

  KGWidget.prototype.setLayout = function (name) {
    this._graph.setLayout(name);
  };

  KGWidget.prototype.openPanel  = function () {
    if (this._panelEl) this._panelEl.classList.remove('kg-panel-hidden');
  };
  KGWidget.prototype.closePanel = function () {
    if (this._panelEl) this._panelEl.classList.add('kg-panel-hidden');
  };

  KGWidget.prototype.destroy = function () {
    if (this._graph) { this._graph.destroy(); this._graph = null; }
    this._container.innerHTML = '';
    this._container.classList.remove('kg-widget', 'kg-light');
  };

  global.KGGraph  = KGGraph;
  global.KGWidget = KGWidget;

}(typeof window !== 'undefined' ? window : this));
