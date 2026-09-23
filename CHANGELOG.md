<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Changelog

## Unreleased

### Added

- `mas-ctl compile`: dump the resolved Agent or MAS spec after overlay merge
  and runtime default resolution (`--layout tree|bundle`, `--output` folder
  or file). See [docs/cli/compile.md](docs/cli/compile.md).
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
  `spec.skills`, or `spec.prefer_local` — the `FlavourSeparationValidator`
  rejects them at load time. Move model choice / inference params / RAG
  config to the agent's `kind: Agent` spec. Offline LLM turns use
  `llm_cache` replay recorded against a live provider, not a Flavour or
  Agent field. See `docs/schemas/runtime/flavour.schema.yaml` and
  `docs/design/flavour-boundary.md` for the current boundary.
- `spec.execution.mocking` is removed from the execution-binding schema
  (not deprecated). Offline CI records a live provider into
  `tests/fixtures/llm-cache/ci.llm-cache.json` and replays with
  `raise_on_miss`.

## Initial release v0.1
