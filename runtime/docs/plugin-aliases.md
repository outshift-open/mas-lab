<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Plugin Aliases and Discovery

`mas-runtime` resolves plugins by canonical URNs, while humans and manifests may use aliases.

## Roles

| Component | Role |
| --- | --- |
| `mas-runtime` | Owns the runtime registry, default alias manifest, validation, and lookup. |
| `mas-library-standard` | Ships canonical built-in plugin implementations and the default alias data used by the runtime. |
| `config.yaml` | Workspace or user override file for aliases and other runtime configuration. |

## Naming

| Term | Example | Meaning |
| --- | --- | --- |
| Plugin name | `react` | Human-friendly alias used in manifests and CLI inputs. |
| URN | `mas.dp.react` | Canonical runtime identifier. |
| Alias manifest key | `react@v1` | Alternate alias that resolves to the same URN. |

The runtime registry normalizes aliases to canonical URNs before lookup. If more than one plugin matches the same name, attribute filters are applied across all candidates.

## Discovery order

The runtime loads aliases from two sources:

1. Package defaults from [src/mas/runtime/aliases.yaml](../src/mas/runtime/aliases.yaml).
2. Workspace or user overrides from `config.yaml`.

Overrides win on key conflict. That makes local alias changes explicit without patching runtime code.

## Configuration

Use a top-level `aliases:` mapping in `config.yaml`:

```yaml
aliases:
  react: mas.dp.cot
  custom_alias: mas.dp.react
```

The runtime validates this mapping against [src/mas/runtime/aliases.schema.yaml](../src/mas/runtime/aliases.schema.yaml).

## Notes for contributors

- Keep alias defaults in package data, not in registry code.
- Prefer canonical URNs in new manifests and docs, and add aliases only for compatibility or ergonomics.
- When adding or changing alias keys, update the manifest, schema, and tests together.