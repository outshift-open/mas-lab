<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Agent Defaults

`mas-runtime` needs a handful of package-wide defaults for values a manifest
is allowed to omit: the LLM model, the design pattern, and the context
manager. These are data, not Python constants, following the same pattern
as [plugin aliases](plugin-aliases.md).

## Discovery order

1. Package defaults from [src/mas/runtime/defaults.yaml](../src/mas/runtime/defaults.yaml).
2. Workspace or user overrides from `config.yaml`'s `defaults:` block.

Overrides win on a per-key basis — a workspace can override just
`design_pattern` and still inherit the package's default `model`.

## Configuration

```yaml
# config.yaml
defaults:
  model: gpt-4.1-mini
  design_pattern: cot@v1
  context_manager: stack
```

This is validated against
[src/mas/runtime/defaults.schema.yaml](../src/mas/runtime/defaults.schema.yaml)
(and against the root `config.schema.yaml`, which declares the same three
keys under its own `defaults:` property).

## How the values are used

- `model` is exposed via `mas.runtime.agent_defaults.default_model()` /
  `resolve_default_model(workspace=None)`, and is *not* a registry plugin
  type — it's a plain string consumed directly by callers that need an LLM
  model id (e.g. `mas-ctl`'s `resolve_model_name`).
- `design_pattern` and `context_manager` *are* registry spec keys: on
  startup, `bootstrap.load_registry()` reads `defaults.yaml` (merged with
  any `config.yaml` override) via `mas.runtime.registry.defaults.
  load_defaults()` and calls `PluginRegistry.set_default(spec_key,
  plugin_id)` for each one. `agent_defaults.default_pattern_plugin_id()`
  and `default_context_manager_id()` then simply read those back via
  `PluginRegistry.default_for(spec_key)` — there is exactly one source of
  truth for "what plugin does an omitted `spec.design_pattern` resolve to."

A plugin manifest (`library.yaml`, or a split-out `*.plugins.yaml`) can
*also* declare its own `defaults:` block (see
[plugin-registry-manifests.md](plugin-registry-manifests.md)) to set the
default for a type it introduces. That is scoped to a single manifest's
own plugin types and complements this mechanism, which is the runtime-wide
default for `model`, `design_pattern`, and `context_manager`.

## Notes for contributors

- Keep default values in package data (`defaults.yaml`), not in Python
  constants or registry bootstrap code.
- When adding a new package-wide default key, add it to both
  `defaults.schema.yaml`'s `spec` properties and `config.schema.yaml`'s
  `defaults` properties, and decide whether it needs a registry
  `set_default()` call in `bootstrap.load_registry()` (only spec keys that
  are also registry plugin types do) or just a plain accessor (like
  `model`).
- `agent_defaults.py`'s public API is `default_model()`,
  `resolve_default_model(workspace=None)`, `default_pattern_plugin_id()`,
  and `default_context_manager_id()`.
