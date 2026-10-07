<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS Framework — Hands-On Tutorials

Progressive tutorials for the MAS Framework — from single-agent basics to full
lab experiments. They are one of several ways to work with MAS Lab; you can also
[reproduce paper labs](../paper/index.md) or use the [Web UI](../ui/index.md) to
design and inspect agents and experiments.

**Start with Tutorial 0** — Docker or developer install, LLM credentials, and
verification. Same setup for CLI and web UI.

| # | Tutorial | What you learn |
| --- | --- | --- |
| 0 | [Environment Setup](00-environment-setup/) | Install, PATH, model endpoint, API key wiring |
| 1 | [Build an agent](01-building-an-agent/) | Agent manifest, tools, skills, memory, CLI, traces |
| 2 | [Orchestrate your MAS](02-creating-a-mas/) | MAS manifest, delegation, topology overlays |
| 3 | [Run an experiment](03-experiments-and-analysis/) | Experiments, benchmarks, pipelines, MCEv1 evaluation |
| 4 | [MCP tools](04-mcp-tools/) | Discover and dispatch local and remote tools through a stable contract |
| 5 | [A2A agents](05-a2a-agents/) | Discover and dispatch local and remote agents through a stable contract |
| 6 | [Agent skills](06-agent-skills/) | Teach an agent a reusable skill — procedure, reference material, checked script — without folding it into the agent's own instructions |
| 8 | [Telemetry](08-telemetry/) | Native traces, live OTel, replay, collector / ClickHouse |
| 9 | [KG & OXP](09-kg-oxp/) | Native→KG, OTel→KG (OXP `norm`), Neo4j serialization |
| 10 | [Evaluation metrics](10-evaluation-metrics/) | Stock MCE, one-off prompts, reusable EvalMetrics, judge infra |
| 11 | [Sessions and recovery](11-sessions-and-recovery/) | Checkpoint, fork, resume and recover a conversation |
| 12 | [Spawned subagents](12-subagents/) | Run bounded, pre-authored subagent templates during a turn |
| 13 | [Control attach and debug scripts](13-control-and-debug/) | Interrupt a bad session, persist, resume; investigate; steer-to-fix on the restarted chat; auto-checkpoint tree; gdb `script_file` / `--debug-script` |
| 14 | [Governance and HITL](14-governance-hitl/) | Require human or automated-policy approval before a tool call runs |

After Tutorial 14, reproduce all paper results across 3 labs: [Paper](../paper/index.md).

Start from [Tutorial 0](00-environment-setup/README.md) for install and first commands —
CLI and optional [web UI](../ui/index.md) use the same setup.

## Quick start

See **[Tutorial 0 — Environment setup](00-environment-setup/README.md)** for Docker and
developer install paths, LLM credentials, and verification steps.

Tutorials 0–3 ship `demo/scenario.yaml` files with structured steps, commands,
and expected output used by `tests/tutorials/test_scenario_commands.py`.

**Replay all offline commands with logs** (stdout/stderr per tutorial under `/tmp`):

```bash
python scripts/run_tutorial_scenarios.py
# Live LLM steps too:
TUTORIAL_ONLINE=1 python scripts/run_tutorial_scenarios.py
# Logs: /tmp/tutorial-00.log … /tmp/tutorial-03.log
```

**Telemetry** is Tutorial 8 (`mas-library-telemetry`). **Knowledge-graph
normalization** is Tutorial 9 (`mas-library-kg`): native→KG and OTel→KG
(OXP `norm` wrap).

## What's next

After Tutorial 14:

- **Labs** — runnable experiment artifacts live in [`labs/`](../../labs/): `design-space.lab` (design patterns + topologies), `lifecycle-control.lab`, `extensions.lab` — see [paper index](../paper/index.md). Lab vs library: [labs-and-libraries.md](../labs-and-libraries.md)
- **Protocol references** — see the [MCP ToolServerRegistry reference](../references/tool-server-registry.md) and [A2A developer reference](../a2a/developer.md)
