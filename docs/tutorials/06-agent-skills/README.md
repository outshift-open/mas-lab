<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 6 — Teaching an Agent a Reusable Skill

> **Packages:** `mas-ctl`, `mas-library-skills`, `agentskills`, `skill-sandbox`
> **Time:** ~35 min hands-on
> **Goal:** Turn a general-purpose agent into a reliable science-answer agent
> that follows a reusable procedure, consults a reference, and runs a checked
> calculation without adding those instructions to the agent itself.
> **Prerequisite:** [Tutorial 0](../00-environment-setup/README.md) for installation and
> LLM access. Familiarity with agents and overlays from
> [Tutorial 1](../01-building-an-agent/README.md) is helpful but not required.

---

## The problem we will solve

Suppose several agents need to answer science questions in the same format:

- state the direct answer first;
- use an authoritative value and preserve its units;
- show useful conversions;
- say how confident the answer is.

Putting these rules in every agent prompt would duplicate them. It would also
load every detail into the model's context, even for unrelated questions.

In this tutorial, you will keep a small general-purpose agent and add an
`answer-expert` skill as a separate directory. By the end, this command will
produce a structured answer using the skill's reference and conversion script:

```bash
mas-ctl chat docs/tutorials/06-agent-skills/agent.yaml \
  -o docs/tutorials/06-agent-skills/overlays/with-skills.yaml \
  --trace \
  -q "What is the speed of light in kilometres and miles per second? Use the answer-expert skill."
```

The agent manifest will remain unchanged throughout the tutorial.

Run every command below from the repository root. Use a skill when instructions
or supporting files should be shared by several agents or loaded only for
particular tasks. Keep a simple, agent-specific instruction in the agent role
when it is always needed and will not be reused.

## What is an Agent Skill?

An Agent Skill is a directory that follows the
[agentskills.io specification](https://agentskills.io/). Its required
`SKILL.md` file contains two kinds of information:

1. A short name and description, which help the agent decide when the skill is
   relevant.
2. Detailed instructions, which are loaded only when the agent chooses the
   skill.

A skill can also contain reference documents, scripts, and other files. This
keeps reusable expertise separate from the agent that uses it.

The example for this tutorial is complete and local:

```text
docs/tutorials/06-agent-skills/
├── agent.yaml
├── overlays/
│   └── with-skills.yaml
└── skills/
    └── answer-expert/
        ├── SKILL.md
        ├── references/
        │   └── physical-constants.md
        └── scripts/
            └── convert_speed.py
```

## Step 1 — Run the agent without the skill

The starting agent is deliberately ordinary:

```yaml
apiVersion: mas/v1
kind: Agent

metadata:
  name: skill-tutorial-agent

spec:
  description: "Answer general knowledge questions."
  context:
    role: |
      Answer the user's question clearly. Do not invent facts that you cannot
      support.
```

Validate it from the repository root:

```bash
mas-ctl validate docs/tutorials/06-agent-skills/agent.yaml
```

Then ask the target question without an overlay:

```bash
mas-ctl chat docs/tutorials/06-agent-skills/agent.yaml \
  -q "What is the speed of light in kilometres and miles per second?"
```

The answer may be correct, but its format, source information, conversions,
and confidence statement depend entirely on the model. This is our baseline.

## Step 2 — Describe when the skill applies

Open `skills/answer-expert/SKILL.md`. It starts with a small YAML block:

```yaml
---
name: answer-expert
description: >
  Use when answering factual science questions that require a direct answer,
  supporting evidence, unit conversions, and an explicit confidence statement.
tags: [science, factual-answers, verification]
---
```

This block is the skill's catalog entry. MAS-Lab shows only this compact entry
to the model at the beginning of a session. The description must therefore say
when to use the skill, not merely what the skill is called.

The Markdown below the YAML block contains the procedure:

```markdown
# Answer Expert

1. Load the relevant file from `references/` before answering.
2. Use `run_skill_script` when the question asks for a conversion supported by
   a script in this skill.
3. Start with a one-sentence direct answer.
4. Follow with the source value, assumptions, and conversions.
5. End with `Confidence: HIGH`, `MEDIUM`, or `LOW` and one short reason.
```

This longer body is not loaded until the model calls
`activate_skill("answer-expert")`.

## Step 3 — Add a reference and a calculation

The file `references/physical-constants.md` contains the exact speed of light
in vacuum and explains the conditions under which it applies. The agent reads
that file only after activating the skill and deciding it is relevant.

The script `scripts/convert_speed.py` converts metres per second to kilometres
and miles per second. You can run it directly to understand its result:

```bash
python docs/tutorials/06-agent-skills/skills/answer-expert/scripts/convert_speed.py \
  299792458
```

Expected output:

```json
{"kilometres_per_second": "299792.458", "miles_per_second": "186282.397"}
```

When the agent runs the same script through `run_skill_script`, MAS-Lab limits
its execution time and memory, removes sensitive environment variables, and
prevents it from reading paths outside the skill directory. A skill script is
still code: review it before adding the skill to an agent.

## Step 4 — Attach the skill with an overlay

The overlay adds one entry to the agent's `skills` list:

```yaml
apiVersion: mas/v1
kind: Overlay

metadata:
  name: with-answer-expert

spec:
  target:
    kind: Agent
  patch:
    skills:
      $op:
        add:
          - answer-expert
```

`$op: add` means "append this item to the existing list." It preserves skills
already declared by the agent or by earlier overlays.

Validate the composed agent:

```bash
mas-ctl validate docs/tutorials/06-agent-skills/agent.yaml \
  -o docs/tutorials/06-agent-skills/overlays/with-skills.yaml
```

The overlay changes the capabilities available to the agent. It does not copy
or edit `agent.yaml`, so the skill can be added to another agent in the same
way.

## Step 5 — Run the complete path

Run the same question again, now with the skill and a trace:

```bash
mas-ctl chat docs/tutorials/06-agent-skills/agent.yaml \
  -o docs/tutorials/06-agent-skills/overlays/with-skills.yaml \
  --trace \
  -q "What is the speed of light in kilometres and miles per second? Use the answer-expert skill."
```

The wording will vary, but the answer should now contain:

- the exact value in metres per second from the reference;
- the converted values produced by the script;
- the condition "in vacuum";
- a confidence statement and reason.

If the model does not use the skill, make the request explicit as shown above.
Skill selection is a model decision; the catalog description gives the model
the information needed to make it.

## Step 6 — See how information is loaded only when needed

Four small actions happen during the run:

| Moment                  | What the agent receives        | Why                                  |
| ----------------------- | ------------------------------ | ------------------------------------ |
| Session starts          | Skill name and description     | Decide whether the skill applies     |
| Skill is selected       | Full `SKILL.md` instructions   | Follow the procedure                 |
| A source is needed      | One file from `references/`    | Read only relevant evidence          |
| A calculation is needed | Output from one script         | Use a deterministic result           |

The runtime provides tools for these actions:

| Tool | Purpose |
| --- | --- |
| `activate_skill` | Load the instructions in `SKILL.md` |
| `list_skill_files` | List references, scripts, and assets in the skill |
| `read_skill_file` | Read one selected file |
| `run_skill_script` | Run one script from the skill's `scripts/` directory |

This is called **progressive disclosure**: the model sees the minimum useful
information first and loads details only when they become necessary. With many
skills, this avoids filling every prompt with instructions unrelated to the
current question.

The trace created beside the manifest lets you confirm the calls:

```bash
grep -E 'activate_skill|read_skill_file|run_skill_script' \
  docs/tutorials/06-agent-skills/traces/events.jsonl
```

## Step 7 — Reuse or replace the implementation

The default implementation is MAS-Lab's native skills support. It reads the
agentskills.io directory directly and runs scripts with `skill-sandbox`.

If an application already uses Google ADK or LangChain, MAS-Lab also provides
adapters for those implementations. They use the same skill directory but
delegate loading and execution to the selected framework. These adapters need
their corresponding optional package extras and deployment configuration, so
they are not required for this tutorial.

Use the native implementation unless the surrounding application already
depends on another framework. The portable part is the skill directory and its
agentskills.io structure; the implementation that loads it is replaceable.

## What you built

You started with a general-purpose agent and added a reusable method for
answering science questions. The final system separates three concerns:

| Concern                                                               | File                        |
| --------------------------------------------------------------------- | --------------------------- |
| What the agent does                                                   | `agent.yaml`                |
| Which reusable skill it may use                                       | `overlays/with-skills.yaml` |
| How to answer, which source to read, and which calculation to run     | `skills/answer-expert/`     |

The same agent can run without the overlay, with this skill, or with a different
skill. [Tutorial 14](../14-governance-hitl/) applies the same separation to
operational control: instead of teaching the agent how to act, you decide
which actions require human approval.

## Troubleshooting

**The skill is not found.** Run the command from the repository root and keep
the `skills/` directory beside `agent.yaml`. Check that the frontmatter `name`
exactly matches the name in the overlay.

**The answer ignores the reference or script.** Ask the model explicitly to use
`answer-expert`, then inspect the trace for the three tool calls shown above.

**The script cannot run.** Run it directly with the Step 3 command first. Skill
scripts must be inside the selected skill's `scripts/` directory.

For broader reuse and discovery rules, continue with the
[skills user guide](https://github.com/outshift-open/mas-lab/blob/main/library-skills/docs/user-guide.md).
For the file format itself, see [agentskills.io](https://agentskills.io/).
