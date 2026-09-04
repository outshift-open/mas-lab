<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Changelog

## Unreleased

### Added

- `library-skills`: an [agentskills.io](https://agentskills.io)-compatible
  implementation of the Agent Skills spec, with three swappable execution
  backends (native filesystem, google-adk, deepagents/LangChain). Agents
  declare skills via `spec.skills` and get progressive disclosure
  (`activate_skill` / `list_skill_files` / `read_skill_file` tools) plus
  optional sandboxed script execution (`run_skill_script`).

### Breaking

- The old `context_manager.params.skills` field (agent + overlay schemas) has
  been removed, along with the `mas.plugin.skill.builder` registry entry that
  backed it. Skill injection is now done via `spec.skills` +
  `SkillCatalogPlugin` (see `library-skills`) instead of the
  `ContextFacetProvider`-based mechanism.
- Flavour manifests (`kind: Flavour`) may no longer carry `spec.llm`,
  `spec.skills`, `spec.mocking`, or `spec.prefer_local` — the
  `FlavourSeparationValidator` now rejects them at load time. Move model
  choice / inference params / RAG config to the agent's `kind: Agent` spec,
  and mocking/cache to the `mas/v1` overlay's `spec.patch.execution` block.
  See `docs/schemas/runtime/flavour.schema.yaml` and
  `docs/design/flavour-boundary.md` for the current boundary.

## Initial release v0.1
