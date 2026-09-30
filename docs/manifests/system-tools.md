<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# System tools

System tools are tools that the runtime owns and implements. Agent authors do
not write them. Examples are loading a skill, running a skill script, asking
the user a question, and sending the user a progress update.

They reach the model through the same `ToolContract` as application tools.
Unlike application tools, they are not loaded from a `kind: Tool` manifest.
Each tool is either **implicit**, meaning another part of the manifest implies
it, or **declared**, meaning it is listed by name.

The full list, with arguments and parameters, is in the
[system tools reference](../references/system-tools.md).

## Rule: the manifest lists what the model sees

An agent is offered a system tool only when one of these conditions is true:

1. **Implicit.** Another part of the manifest requires the tool.
2. **Declared.** `spec.tools` contains `{kind: system, name: <tool>}`.
3. **Host-requested.** The embedding host passes the tool in `system_tools`.
   This is a programmatic API; see [Host-requested tools](#host-requested-tools).

No boolean enables every system tool at once. An agent with no skills and no
declarations gets no system tools.

## Implicit enablement

| Tool(s) | Enabled when |
| --- | --- |
| `activate_skill`, `list_skill_files`, `read_skill_file` | `spec.skills` lists at least one skill |
| `run_skill_script` | a listed skill ships a non-empty `scripts/` directory |
| `run_skill_script` | a `context_sources` plugin sets `auto_inject: true` |

These tools follow from the skills themselves. Listing a skill without a way to
load it would leave the model with a catalog entry it cannot use. Shipping
scripts without `run_skill_script` would leave instructions the model cannot
follow.

```yaml
spec:
  skills:
    - answer-formatting        # → activate_skill (+ list/read)
    - log-analyzer             # has scripts/ → run_skill_script
```

## Declared enablement

List a system tool in `spec.tools` with `kind: system`. The same entry carries
its `params`:

```yaml
spec:
  tools:
    - ref: ./tools/calculator.tool.yaml
    - kind: system
      name: request_human_input
      params:
        timeout: 300
        auto_resolve_decision: reject
    - kind: system
      name: inform_user
      params:
        max_message_length: 8000
```

Declaration is the only way to enable the user-communication tools,
`request_human_input` and `inform_user`. They are never implicit. If a model
asks the user when nothing in the protocol can answer, it can substitute a
made-up or rubber-stamped answer for a real one, and the caller cannot detect
the substitution. An agent should get these tools only when its deployment can
route questions and updates to a real user.

You can also declare the skill tools explicitly, for example to offer
`run_skill_script` for a skill whose scripts are resolved elsewhere.

An unknown name, such as a typo, fails at load time and lists the available
names. The runtime does not silently skip it.

## Host-requested tools

A program that embeds the runtime can add system tools without editing the
manifest:

```python
build_manifest_tool_provider(
    tools_spec,
    manifest_dir,
    system_tools=["request_human_input", "inform_user"],
)
```

Host-requested names are merged with the manifest declarations. The manifest
still supplies their `params`.

## Overlays

`spec.tools` is merged with `list_ops`, so an overlay can enable a system tool
for one environment without changing the base agent:

```yaml
# overlays/interactive.yaml
spec:
  tools:
    $op:
      add:
        - kind: system
          name: request_human_input
```

The same agent can run in batch mode without HITL and interactively with it.
Only the overlay changes.

## See also

- [System tools reference](../references/system-tools.md). Every tool, with
  arguments, parameters, and where it is implemented.
- [Agent manifest](agent.md). `spec.tools` and `spec.skills` fields.
- [Tutorial 1: skills](../tutorials/01-building-an-agent/README.md). The
  implicit `activate_skill` in practice.
