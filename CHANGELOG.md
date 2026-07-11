<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Changelog

## Unreleased

### Breaking

- Flavour manifests (`kind: Flavour`) may no longer carry `spec.llm`,
  `spec.skills`, `spec.mocking`, or `spec.prefer_local` — the
  `FlavourSeparationValidator` now rejects them at load time. Move model
  choice / inference params / RAG config to the agent's `kind: Agent` spec,
  and mocking/cache to the `mas/v1` overlay's `spec.patch.execution` block.
  See `docs/schemas/runtime/flavour.schema.yaml` and
  `docs/design/flavour-boundary.md` for the current boundary.

## Initial release v0.1
