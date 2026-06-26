<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-ctl Developer Guide

This guide covers extending orchestration behavior while keeping `mas-ctl` declarative and library-centric.

## Architecture

`mas-ctl` should remain a thin CLI over reusable orchestration library code.

## Development principles

- Keep orchestration logic in library modules, not command handlers.
- Model topology and policy in manifests first.
- Preserve deterministic resolution order (base + flavour + scenario).

## Extension areas

### Manifest resolution

- Add new schema keys only with explicit validation rules.
- Maintain strict secret-vs-config separation.

### Workflow/topology

- Add topology types with clear execution semantics.
- Provide migration notes when changing default behavior.

### Placement

- Only `local-inproc` is OSS-supported; other strategies are planned for a later release.
- Validate placement strategy at compose time via `placement_validate.validate_placement_strategy`.

### Policy enforcement

- Implement checks as composable components.
- Produce actionable policy errors with context.

## Testing strategy

- Unit tests for manifest parsing and overlay merge behavior.
- Integration tests for representative topologies.
- End-to-end tests with real runtime/lab coupling where needed.

## Developer checklist

- New config fields documented
- Effective config output updated
- CLI help updated
- Backward-compatibility implications documented
