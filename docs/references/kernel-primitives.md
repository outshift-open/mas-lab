<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Kernel operations — what they are, and how existing harnesses use them

The runtime stays small. It does not grow a debugger product, a subagent
engine, or an evolution engine. Those are the same operations, used in
different orders.

## Operations

| Operation | Meaning |
| --- | --- |
| Start / stop an agent | Turn a spec into a running agent, and tear it down |
| Take a step | Current state + input → next state, through governance, written to the trace |
| Start a child | Another running agent with a parent id (a subagent) |
| Snapshot | Cheap in-memory picture of where the run is |
| Persist | Write that picture to disk so it survives a restart |
| Walk the tree | Move a debug cursor; does not change the live run until promote |
| Pause / resume / steer / undo | Control. Pause actually blocks the next user turn |
| Change the spec | Disable a tool, switch a pattern, apply a factor — recorded revision |

A plugin author, the LLM (as a tool), and an operator (CLI/admin) all
call these same functions. The LLM tool is only an advertisement.

## Existing harnesses as combinations

| What people call it | Combination |
| --- | --- |
| ReAct | one agent + tools + governance |
| Plan-and-execute / tree-of-thought | same + branch / undo |
| Static multi-agent | several started agents + run a turn on each |
| Subagents | start a child + parent id + stop the child |
| OpenClaw-style recovery | snapshot on events + undo + steer |
| Debugger / detective | pause + walk the tree + branch to investigate |
| What-if | N branches from one snapshot, score, throw away |
| Evolutionary / population | N branches + spec revisions + keep or throw away |

If a new harness cannot be written as a row in this table, either an
operation is missing (justify it first) or it does not belong in the kernel.
