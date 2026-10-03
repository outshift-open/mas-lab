<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# CLI Override Reference

The general CLI override syntax lets a command patch a loaded manifest or
in-memory configuration without creating a temporary overlay file:

```text
--override ROOT:PATH=VALUE
```

Every override is converted to a canonical `apiVersion: mas/v1`,
`kind: Overlay` document and is processed by the same normalization, merge,
operator, and validation code as a file overlay. Overrides are applied after
all `--overlay` files and after legacy inline flags.

## Quick examples

```bash
# Agent field
mas-ctl chat agent.yaml \
  --override 'agent:spec.context.role="security reviewer"'

# Add a tool with the existing overlay operator
mas-ctl chat agent.yaml \
  --override 'agent:spec.tools={"$op":{"add":["web-search"]}}'

# Select one agent inside a MAS
mas-ctl run-mas mas.yaml \
  --override 'mas:spec.agency.agents[id=reviewer].spec.memory=long'

# Fan out to every MAS agent
mas-ctl run-mas mas.yaml \
  --override 'mas:spec.agency.agents[*].spec.context.environment=staging'

# Compile an effective manifest
mas-ctl compile mas.yaml \
  --override 'mas:spec.models[id=main].model="gpt-test"'

# Benchmark experiment configuration
mas-lab benchmark run experiment.yaml \
  --override 'experiment:experiment.run.n_runs=1' \
  --override 'experiment:experiment.dataset.limit=2'

# Workspace values are changed only in memory for this invocation
mas-ctl chat agent.yaml \
  --override 'workspace:defaults.model="gpt-test"'

# Address a context key containing dots
mas-ctl chat agent.yaml \
  --override 'agent:spec.context["key.with.dots"]=value'
```

## Manifest tree

The path starts at a named root. The root identifies the document before the
path walks through its YAML tree.

```text
workspace/config.yaml
  |
  +-- experiment.yaml ---------------------- experiment:experiment.*
  |                                            |
  |                                            +-- application (MAS binding)
  |                                            +-- scenarios
  |                                            +-- dataset
  |                                            +-- run / pipeline
  |
  +-- mas.yaml ----------------------------- mas:spec.*
  |       |
  |       +-- spec.agency.agents[id=planner]
  |                    |
  |                    +-- ref: agents/planner.yaml
  |                    +-- inline spec
  |
  +-- agent.yaml --------------------------- agent:spec.*
  |       |
  |       +-- tools, skills, models
  |       +-- context, memory, governance
  |
  +-- infra refs --------------------------- infra:spec.*
  +-- flavour ------------------------------ flavour:spec.*
```

The path is explicit because `spec.tools` can belong to a standalone Agent,
an entry Agent inside a MAS, or an infrastructure provider. The command decides
which roots are loaded; an unavailable root is an error, not a silent no-op.

## Supported roots

| Root | Typical commands | Meaning |
| --- | --- | --- |
| `agent` | `chat`, `compile` | Standalone Agent manifest |
| `mas` | `run-mas`, `compose`, `compile` | MAS or Workflow manifest |
| `infra` | `chat`, `run-mas`, `compose` | Effective merged infrastructure |
| `flavour` | runtime composition | Effective deployment flavour |
| `experiment` | `mas-lab benchmark run` | Experiment before validation and expansion |
| `workspace` | `chat`, `run-mas` | In-memory effective workspace/config values |

An entry Agent inside a MAS is addressed through the MAS root:

```text
mas:spec.agency.agents[id=planner].spec.tools
```

It is deliberately different from:

```text
agent:spec.tools
```

The latter addresses a standalone Agent document.

## Path syntax

The path grammar is:

```text
assignment := ROOT ":" path "=" yaml-value
path       := segment ("." segment)*
segment    := identifier | identifier "[" selector "]"
selector   := integer | identity | "*"
identity   := key "=" yaml-scalar
```

Examples:

```text
agent:spec.context.role
agent:spec.models[id=main].model
mas:spec.agency.agents[id=planner].spec.context.role
mas:spec.agency.agents[0].spec.memory
mas:spec.agency.agents[*].spec.context.environment
infra:spec.tool_servers[id=mcp].port
experiment:experiment.run.n_runs
workspace:defaults.model
```

Identity selectors are preferred over numeric indexes because indexes can move
when an overlay adds or removes list entries. A selector that matches no entry
fails with an error listing the requested identity. Wildcards expand in
manifest order and apply the same operation to every match.

Intermediate path segments must already exist. The final key may be absent
only when the target schema declares it, so
`agent:spec.models[*].max_tokens=4096` adds `max_tokens` to every model row
while a typo such as `max_tokenz` is rejected.

Quoted mapping-key selectors keep dots and brackets inside a map key instead of
treating them as path separators:

```text
agent:spec.context["key.with.dots"]
```

## Values

Values are parsed as YAML values after shell parsing:

```bash
--override 'agent:spec.enabled=true'       # boolean
--override 'agent:spec.max_steps=10'        # integer
--override 'agent:spec.temperature=0.2'     # number
--override 'agent:spec.name="qa agent"'     # string
--override 'agent:spec.tags=[qa,fast]'       # list
--override 'agent:spec.params={mode: safe}'  # map
```

Quote the entire assignment in the shell when it contains `$`, brackets,
spaces, braces, or quotes. The value is validated again against the target
schema after merge.

## Operators

The same `$op` forms accepted by file overlays are accepted by CLI overrides
where the target field's `x-merge` strategy supports them:

```bash
# Replace a collection
--override 'agent:spec.tools={"$op":{"replace":["calculator"]}}'

# Append to a list
--override 'agent:spec.tools={"$op":{"add":["web-search"]}}'

# Remove from a list
--override 'agent:spec.tools={"$op":{"remove":["calculator"]}}'

# Clear a collection
--override 'agent:spec.skills={"$op":{"clear":true}}'

# Merge a mapping
--override 'agent:spec.context={"$op":{"merge":{"role":"reviewer"}}}'
```

Raw values use the field's normal overlay behavior. For example, a raw list
means replacement for a `list_ops` field, while a named list uses its schema
declared identity strategy.

## Grouping overrides in an overlay manifest

An `Overlay` manifest can carry an ordered `spec.overrides` list when the same
selector-based changes should be reused by scenarios or several commands. Each
item uses the same `ROOT:PATH=VALUE` syntax as the CLI, and is applied after the
manifest's regular `spec.patch`:

```yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: review-policy
spec:
  target: {kind: MAS}
  patch: {}
  overrides:
    - 'mas:spec.agency.agents[id=reviewer].spec.memory=long'
    - 'mas:spec.agency.agents[*].spec.context.environment=staging'
```

The root must match the overlay target kind. Identity selectors and wildcards
operate on entries already present in the effective document; an unmatched
selector is an error. The overlay is still validated as a normal `mas/v1`
Overlay, and source manifests remain unchanged.

## Priority

The effective order is:

```text
workspace/config defaults
  < base manifest
  < file overlays in argument order
  < legacy shortcut flags
  < --override arguments in argument order
  < runtime defaults for fields still absent
```

The later CLI override wins when the field strategy allows multiple writes.
Conflicting wildcard operations or unsupported operations fail rather than
using accidental dictionary ordering.

## Legacy shortcuts

Existing flags remain supported:

| Existing flag | Equivalent intent |
| --- | --- |
| `--tool NAME` | Add `NAME` to `agent:spec.tools` |
| `--skill NAME` | Add `NAME` to `agent:spec.skills` |
| `--memory ID` | Replace `agent:spec.memory` |
| `--set KEY=VALUE` | Set an Agent context value |
| `--max-tokens N` | Alias of `--override 'agent:spec.models[*].max_tokens=N'`, placed before explicit `--override` values (`chat`, `tui`) |
| `--overlay PATH` | Load a file Overlay before CLI values |
| `--scenario-id ID` | Benchmark selection shortcut |
| `--dataset-item ID` | Benchmark dataset selection shortcut |

These flags remain the compatibility interface for common operations. General
`--override` is the explicit interface when the path, root, selector, or merge
operation matters.

## References and safety

Overrides never rewrite source YAML files or `config.yaml`. They operate on the
effective in-memory document for one command invocation.

For ref-based MAS agents, address the entry through the MAS path. The document
must be materialized by the command before a nested field can be selected. Use
an explicit identity selector rather than relying on list position:

```bash
mas-ctl run-mas mas.yaml \
  --override 'mas:spec.agency.agents[id=planner].spec.context.role=planner'
```

Invalid roots, paths, selectors, operations, or final schema values fail before
runtime execution. Diagnostics include the original override expression and the
failing root/path.

Schemas may mark a field with `x-cli: {allowed: false}` to protect generated or
runtime-owned values. Such a path is rejected before merge.

Related references:

- [mas-ctl command reference](mas-ctl.md)
- [Overlay manifest](../manifests/overlay.md)
- [Schema index](../references/schemas.md)
- [Experiment manifest](../manifests/experiment.md)
- [Infra manifest](../manifests/infra.md)
