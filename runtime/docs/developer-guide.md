<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-runtime Developer Guide

This guide covers extending `mas-runtime` with plugins, tools, and overlays while preserving contract and hook semantics.

## Architecture snapshot

`mas-runtime` is a library-first runtime. The CLI wraps builder/runtime APIs and should not own core orchestration logic.

## Extension points

### Plugins

- Implement plugin interfaces using runtime contract expectations.
- Keep plugin responsibilities narrow (governance, memory, observability, tools, transport).
- Use consistent naming prefixes when relevant (`gov_`, `ctx_`, `obs_`, `tool_`, `dp_`).

### Tools

- Implement `ToolContract` with explicit input schema.
- Prefer deterministic side effects and idempotent external calls.
- Emit structured errors for policy and retry layers.

### Overlays and flavours

- Overlays compose behavior (reasoning or policy) without mutating base manifests.
- Flavours separate environment concerns from application concerns.

## Dev workflow

1. Implement feature in `src/`.
2. Register/export in package entrypoints.
3. Add unit tests in `tests/` for happy path + failure path.
4. Validate with CLI smoke test.

## Testing guidance

- Contract tests for plugin hook order and payload integrity
- Tool tests for schema validation and error handling
- Integration tests for manifest+flavour loading
- Regression tests for trace and artifact shape

## API and contract references

- `docs/dev/contracts/index.md`
- `docs/dev/contracts/taxonomy.md`
- `docs/dev/schemas/agent-manifest.md`
- `docs/dev/schemas/tool-definition.md`
- `docs/dev/api-reference/mas-runtime-api.md`

## Quality bar

- No hardcoded secrets
- No undocumented config keys
- Predictable behavior under retries/timeouts
- Backward-compatibility strategy documented when changing public contracts
