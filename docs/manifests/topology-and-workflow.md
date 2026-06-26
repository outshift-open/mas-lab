<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Topology, workflow, and routing

Three related ideas in MAS manifests — often confused:

| Term | What it is | Where it lives | Example |
| --- | --- | --- | --- |
| **Topology** | Which agents exist and how they relate (team shape) | `MAS.spec.agency.agents`, overlay patches | design-space **Exp 1.2** sweeps five overlays (`topo-linear-pipeline`, `topo-moderator-broker`, `topo-parallel`, `topo-supervised`, `topo-verifier`) |
| **Workflow** | Turn order and who runs when (session choreography) | `MAS.spec.workflow` | Linear: fixed chain; moderator: one specialist at a time; parallel: all specialists per fan-out |
| **Routing logic** | Per-message decisions inside a turn (which tool/delegate next) | LLM + delegation tools, agent prompts | Moderator reads the user message and chooses `schedule_agent` vs `itinerary_agent` |

## In chat — workflow vs routing

Think of a **trip-planning MAS** answering one user message.

**Workflow** is the *stage play*: who is allowed on stage, and in what order.

- **Linear pipeline workflow:** schedule agent always runs first, then itinerary, then concierge — every time, regardless of the question.
- **Moderator-broker workflow:** the moderator runs first, then **one specialist at a time** in an order the moderator chooses across turns.
- **All-parallel workflow:** the moderator still opens the scene, but **all three specialists run in the same act** (`dispatch: parallel`); the moderator aggregates their outputs.

**Routing logic** is what happens *inside* the moderator’s turn when it decides the next move:

- “This is mostly a transport question → delegate to `schedule_agent`.”
- “User asked for hotels and trains → call itinerary, then concierge.”
- “Fan out to everyone because the prompt spans all domains.”

Routing is **per message / per LLM step** (tool calls, delegation targets). Workflow is the **declared graph** ctl enforces (entry node, `delegates_to`, `dispatch: parallel`, sequential edges). You can keep the same agents and topology but change workflow overlays to switch from sequential chain to parallel fan-out without editing agent code.

## Topology in paper labs

[`labs/design-space.lab/02-topologies/`](../../labs/design-space.lab/02-topologies/) varies **topology only** via scenario overlays — no agent code changes.

Example (`topo-moderator-broker`):

```yaml
spec:
  patch:
    workflow:
      entry: moderator
      nodes:
        - id: moderator
          agent: moderator_agent
          delegates_to: [schedule_agent, itinerary_agent, concierge_agent]
```

Compare with `topo-parallel` (fan-out to all specialists at once), `topo-linear-pipeline` (fixed sequence), `topo-supervised`, or `topo-verifier`. Each overlay is one column in the experiment matrix.

## Workflow execution in OSS

| Pattern | ctl behavior |
| --- | --- |
| **Dynamic delegation** | Default multi-agent: entry agent session; LLM uses delegation tools |
| **Sequential graph** | `mas-ctl run-mas` when `workflow.nodes` + `workflow.edges` are set |
| **Single agent** | `topo-single-agent` overlay — one generalist, no inter-agent workflow |

There is no `WorkflowContract.register_impl()` in OSS. Topology + workflow are **declarative** in YAML; ctl composes and runs them.

## Stateful governance (budget)

Separate from topology: **governance plugins** track session state across turns.

[`lifecycle-control.lab`](../../labs/lifecycle-control.lab/) stacks budget caps, guardrails, and HITL. Budget enforcement uses `BudgetTracker` and overlay plugins such as `budget-cap` on `budget_threshold` — an example of **stateful governance** required for paper Exp 2.1.

See [contracts reference](../references/contracts.md#governance) and runtime `boundary/gov/budget.py`.

## See also

- [MAS manifest](mas.md)
- [Workflow manifest](workflow.md) (`workflow/v1` graph form)
- [Scenario overlays](overlay.md)
- [Tutorial: creating a MAS](../tutorials/02-creating-a-mas/README.md)
