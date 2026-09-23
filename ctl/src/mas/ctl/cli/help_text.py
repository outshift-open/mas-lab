#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared CLI help epilogs for mas-ctl commands."""

COMPILE_EPILOG = """
Examples:
  mas-ctl compile agent.yaml -o overlays/tools.yaml -o overlays/skills.yaml
  mas-ctl compile agent.yaml -o overlays/tools.yaml -O compiled-agent.yaml
  mas-ctl compile mas.yaml -o overlays/linear.yaml -O ./compiled/
  mas-ctl compile mas.yaml -o overlays/linear.yaml --layout bundle -O team.yaml

Layouts:
  auto    YAML file or stdout → one document; directory → mas.yaml + agents/
  tree    Always a folder (MAS keeps one file per agent; Agent writes agent.yaml)
  bundle  Always one YAML file (MAS inlines agents into agency.agents)

``compose`` emits EffectiveBind + placement. ``compile`` dumps the resolved spec.
"""

CHAT_EPILOG = """
Interactive session commands (at the You: prompt):
  /quit, /exit, /q     End the session
  /reset               Clear working memory and turn history; restore system prompt
  /steer <text>        Inject operator steering mid-run (updates context)

Governance / HITL (when spec.governance.hitl_on_tool is set):
  Interactive mode (-i) prompts on stderr: SCHEDULE (allow), BLOCK, SKIP
  Batch (-q) auto-approves unless hitl_mode: auto-deny in overlay
  Full-screen HITL: mas-ctl tui (same overlays)

Context model (see docs/design/context-sources.md):
  Working memory  — τ ledger + ctx assembly for the current turn
  Chat history    — prior user/agent turns (ctl session; optional plugin feed)
  Persistent memory — memory plugin (semantic / episodic backends)

Examples:
  mas-ctl chat agent.yaml -i -o overlays/tools.yaml --trace
  mas-ctl chat agent.yaml -i -o overlays/tools.yaml --trace --trace-timestamps
  mas-ctl chat agent.yaml -i -o overlays/tools.yaml --trace -vv

Trace (--trace, or automatic with -i + HITL):
  Exchanges stream on stderr as they happen (AGENT→LLM context, LLM→AGENT replies,
  tool calls/results). --trace-timestamps adds UTC time + elapsed. -vv or
  --trace-engine adds raw engine InvokeEngineIo / EngineIoReturn JSON.
"""
