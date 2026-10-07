<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 14 — Putting Human Approval Around Agent Actions

> **Packages:** `mas-ctl`, `mas-runtime`, `mas-library-standard`
> **Time:** ~40 min hands-on
> **Goal:** Build a budget assistant that can calculate a total but cannot run
> its calculator until a human or an explicit automated policy approves the
> action.
> **Prerequisite:** [Tutorial 0](../00-environment-setup/README.md) for installation and
> LLM access. [Tutorial 1](../01-building-an-agent/README.md) introduces overlays;
> [Tutorial 6](../06-agent-skills/README.md) shows the same separation for reusable
> knowledge rather than operational control.

---

## The problem we will solve

Agents often need tools to do useful work. Some tools only read data; others
send messages, alter records, spend money, or expose sensitive results. A prompt
such as "ask before acting" is not a reliable control because the model itself
decides whether to follow it.

This tutorial moves that decision outside the model. We will start with a
budget assistant, add a calculator, and then place an approval rule around every
tool call. By the end:

1. the agent proposes a calculation;
2. MAS-Lab pauses before running it;
3. an operator approves or rejects the operation;
4. the trace records what was requested and how it was resolved.

The complete example lives in this tutorial directory:

```text
docs/tutorials/14-governance-hitl/
├── agent.yaml
└── overlays/
    ├── tools.yaml
    ├── governance-interactive.yaml
    ├── governance-auto-approve.yaml
    ├── governance-auto-deny.yaml
    └── agent-asks-user.yaml
```

Run every command below from the repository root. Use this pattern when an
operation needs an enforceable approval or denial. A prompt instruction is
enough only when occasional model judgment is acceptable and no external
control or audit trail is required.

## Governance and human approval in plain language

In MAS-Lab, **governance** means rules that inspect a proposed operation before
or after it crosses the agent boundary. **Human-in-the-loop (HITL)** means one
of those rules pauses the operation and asks a person to decide.

For this tutorial, remember three moments:

```text
agent proposes tool call
        |
        v
rule asks for approval  ---> reject: tool does not run
        |
      approve
        v
tool runs and returns a result
        |
        v
optional second approval before the model sees the result
```

The rule is enforced by the runtime. The agent cannot bypass it by changing its
answer or tool arguments.

## Step 1 — Start with the budget assistant

The base agent contains no tool and no approval rule:

```yaml
apiVersion: mas/v1
kind: Agent

metadata:
  name: governed-budget-agent

spec:
  description: "Calculate and explain simple project budgets."
  context:
    role: |
      Help the user calculate a project budget. Show the expression used and
      explain the result. Use the calculator when it is available.
```

Validate it from the repository root:

```bash
mas-ctl validate docs/tutorials/14-governance-hitl/agent.yaml
```

At this point the agent can reason about a budget, but it cannot call a
calculator.

## Step 2 — Add the calculator

The first overlay adds the calculator from the sample library. The `samples:`
prefix names the installed `mas-library-samples` package, so the manifest can
refer to a reusable tool without depending on a relative filesystem path:

```yaml
spec:
  patch:
    tools:
      $op:
        add:
          - ref: samples:tools/calc.tool.yaml
```

`$op: add` appends the calculator to any tools already available on the agent.
The same operation is used for the governance rules in the next step.

Run the assistant with that overlay:

```bash
mas-ctl chat docs/tutorials/14-governance-hitl/agent.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/tools.yaml \
  -q "A workshop costs 125 dollars per person for 3 people, plus 42 dollars for materials. Calculate the total."
```

The agent can now call `calc` with `125 * 3 + 42` and return `$417`. Nothing
yet requires approval, so the tool runs as soon as the model requests it.

## Step 3 — Require an operator before the tool runs

The interactive governance overlay adds a rule on top of the same agent:

```yaml
spec:
  patch:
    governance:
      $op:
        add:
          - sample_governance:
              hitl_on_tool: true
              hitl_on_tool_result: false
              hitl_once_per_turn: false
              hitl_mode: interactive
```

The important setting is `hitl_on_tool: true`: ask a human before every tool
call. Start an interactive session with both overlays:

```bash
mas-ctl chat docs/tutorials/14-governance-hitl/agent.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/tools.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/governance-interactive.yaml \
  --trace -i
```

At the `You:` prompt, enter:

```text
A workshop costs 125 dollars per person for 3 people, plus 42 dollars for materials. Calculate the total.
```

When the agent requests `calc`, the prompt changes from `You:` to `HITL>` and
shows the proposed operation. Enter `ALLOW` to let it run. The agent then
receives the result and answers `$417`.

Run the same command again and enter `BLOCK` at `HITL>`. The calculator
does not run. Depending on the model, the agent may explain that approval was
not granted or continue without the tool. The important result is operational:
the protected action did not execute.

You can use `mas-ctl tui` instead of `mas-ctl chat -i` if you prefer the terminal
interface:

```bash
mas-ctl tui docs/tutorials/14-governance-hitl/agent.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/tools.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/governance-interactive.yaml
```

## Step 4 — Decide whether results also need review

Some operations return sensitive or untrusted data. To inspect a tool result
before it becomes part of the model's working context, change:

```yaml
hitl_on_tool_result: true
```

With both switches enabled, one tool use can pause twice:

1. before the tool runs, to approve the requested operation;
2. after it returns, to approve the data before the model sees it.

This tutorial leaves result review off so the first interaction has one clear
approval. Enable it when the returned content itself requires control.

## Step 5 — Use explicit decisions in batch and CI

An automated job has no person waiting at a terminal. It must state how HITL
requests are resolved. The provided overlays use the same governance rule with
a different `hitl_mode`.

Auto-approve is useful when a test must exercise the complete tool path:

```bash
mas-ctl chat docs/tutorials/14-governance-hitl/agent.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/tools.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/governance-auto-approve.yaml \
  -q "Calculate 125 * 3 + 42."
```

Auto-deny is useful for checking that a protected operation cannot silently run:

```bash
mas-ctl chat docs/tutorials/14-governance-hitl/agent.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/tools.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/governance-auto-deny.yaml \
  -q "Calculate 125 * 3 + 42."
```

Do not rely on an interactive policy in a process with no terminal. Choose
`auto-approve` or `auto-deny` deliberately so the behavior is visible in the
manifest and reproducible in CI.

## Step 6 — Inspect the evidence in the trace

The `--trace` run writes `traces/events.jsonl` beside the agent manifest. Search
for governance and HITL events:

```bash
grep -E 'governance|hitl' \
  docs/tutorials/14-governance-hitl/traces/events.jsonl
```

The exact fields may grow over time, but the trace records the proposed
operation, the rule that evaluated it, the decision, and the reason. This lets
you answer concrete questions after a run:

- Which tool did the agent try to use?
- Was approval required before or after the operation?
- Who or what resolved the request?
- Did the tool run?

This is why governance belongs outside the prompt: the runtime both enforces and
records the decision.

## Step 7 — Let the agent ask a question when information is missing

Policy-driven approval and agent-driven questions solve different problems:

| Situation                                           | Use                                            |
| --------------------------------------------------- | ---------------------------------------------- |
| Every matching operation must be reviewed           | A governance rule such as `hitl_on_tool`       |
| The agent cannot continue without a user choice     | The `request_human_input` system tool          |

The `agent-asks-user.yaml` overlay gives the model access to
`request_human_input`. It also tells the budget assistant to confirm totals over
$400:

```bash
mas-ctl chat docs/tutorials/14-governance-hitl/agent.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/tools.yaml \
  -o docs/tutorials/14-governance-hitl/overlays/agent-asks-user.yaml \
  -i
```

Enter the same `$417` workshop request. The agent can calculate the total and
then ask whether it may accept the total. Enter `ALLOW` or `BLOCK` when the
`HITL>` prompt appears. This request originates from the agent's task
instructions. By contrast, the governance rule in Step 3 applies whether or
not the agent wants to ask.

For high-impact actions, use governance as the mandatory control. Use
`request_human_input` for missing preferences, confirmation, or feedback within
the task.

## Step 8 — Understand the available outcomes

A governance plugin returns a decision, a rule name, and a human-readable
reason. The runtime supports these decisions:

| Decision | Effect |
| --- | --- |
| `ALLOW` | Continue normally |
| `LOG` | Record the decision and continue |
| `HITL` | Pause and request a human or configured automated response |
| `BLOCK` | Refuse the operation |
| `SKIP` | Skip the operation and provide a controlled result |
| `RETRY` | Ask for another attempt |
| `MODIFY` | Replace approved parts of the proposed operation |
| `TERMINATE` | End the session |
| `BLACKLIST` | Prevent further use of the selected tool in the session |

The sample rule used in this tutorial focuses on `HITL`. Applications can add
their own plugins for organization-specific rules.

Here is the smallest useful shape of such a plugin:

```python
from mas.runtime.boundary.gov.plugin import EgressDecision
from mas.runtime.boundary.gov.policy import EgressIntentView
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision


class ReadOnlyToolsOnly:
    def evaluate_egress(
        self, intent: EgressIntentView, *, config: KernelConfig
    ) -> EgressDecision:
        if intent.op == "TOOL_CALL" and intent.tool_name != "approved-search":
            return (
                GovDecision.BLOCK,
                "read-only-tools",
                "only approved-search is allowed",
            )
        return GovDecision.ALLOW, "read-only-tools", "operation is allowed"
```

The method receives a description of the proposed operation and returns what
should happen. In production code, use the typed
[`GovernancePlugin` contract](https://github.com/outshift-open/mas-lab/blob/main/runtime/src/mas/runtime/boundary/gov/plugin.py)
and register the plugin in a library so manifests can refer to it by name.

When several rules are listed, they run in order. An `ALLOW` lets the next rule
check the operation; a `BLOCK` stops immediately. A pending human decision can
still be followed by a stricter rule that blocks the operation.

## What you built

You began with an ordinary budget assistant and added control without changing
its agent manifest:

| Layer | Responsibility |
| --- | --- |
| `agent.yaml` | Define the budget assistant's job |
| `tools.yaml` | Make the calculator available |
| `governance-interactive.yaml` | Require an operator before tool execution |
| `governance-auto-*.yaml` | Make batch behavior explicit and reproducible |
| `agent-asks-user.yaml` | Let the agent request information when the task needs it |

The concrete result is a calculator that remains useful but cannot execute
outside the decision process selected for the deployment.

## Troubleshooting

**No HITL prompt appears.** Confirm that both the tool and governance overlays
are present and use `-i`. The prompt appears only after the model actually asks
to use a tool.

**A non-interactive command blocks or exits.** Use one of the auto-decision
overlays from Step 5 instead of the interactive overlay.

**The trace file is missing.** Add `--trace` to the command. By default, ad hoc
chat traces are written beside the agent under `traces/events.jsonl`.

Continue with the [plugin bindings reference](../../manifests/plugin-bindings.md)
for all manifest options and the
[governance plugin guide](https://github.com/outshift-open/mas-lab/blob/main/library-standard/src/mas/library/standard/plugins/governance/README.md)
for the built-in implementations.
