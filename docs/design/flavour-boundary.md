#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Flavour / infra / overlay / execution boundary

Status: proposal (FT3, `BRANCHES.md` §5b). Blocks FT4 (flavour schema rework)
and FT7 (CLI observability flags as a flavour overlay). Written against the
code as of this branch; file:line references are current as of writing and
will drift — treat them as pointers, not guarantees.

## The tension

`BRANCHES.md` flags four things that look alike in the code today (they all
end up patching an in-memory spec dict) but are conceptually different:

- a **flavour** — deployment posture (protocol, observability/control plugin
  selection)
- **infra** — endpoints, tool name→impl mapping, model wire-names
- **overlay / agent-spec** — llm params, tools, skills, memory
- **execution** — mocking, caching (pipeline elements sitting between the
  agent and the LLM/tool call)

Cache and mocking are called out specifically because they don't obviously
belong to either "flavour" or "infra": a cache is infrastructure-shaped (it
sits in the `InfraMiddleware` chain, `runtime/src/mas/runtime/engine/
infra_pipeline.py:26` — `LlmCacheMiddleware`), but *whether it's on* is a
per-run execution choice, not a fixed piece of environment topology.

## What the code already gets right

This is not a green-field decision — the overlay schema already drew most of
this boundary correctly, independently of the Flavour schema, and the two
disagree. Concretely:

- `docs/schemas/runtime/fragments/execution-binding.schema.yaml` — `spec.patch.execution`
  is explicitly scoped to `mocking.enabled`, `cache.enabled`, `parallel`,
  `live`, `timeout` ("EngineContract execution mode — mock/live/cache/parallel
  only"). `ctl/src/mas/ctl/manifest/spec_bindings.py:246` (`parse_execution`)
  enforces exactly those keys, nothing else.
- `docs/schemas/runtime/infra.schema.yaml` — infra manifests (`InfraBundle`,
  `LLMProxy`, `ToolProvider`, `ToolRegistry`, …) own endpoints, api keys,
  model wire-names, and tool name→impl mapping. Flavours are explicitly
  forbidden from carrying `infra_refs` (`FlavourSeparationValidator`,
  referenced in `flavour.schema.yaml:24`).
- `docs/schemas/runtime/fragments/observability-binding.schema.yaml` — a
  closed plugin-list shape (`native`, `otel`, each with a couple of
  whitelisted config keys) already matches "flavour selects
  observability/control plugins" from the guiding principle in
  `BRANCHES.md` §5b.

**Resolution: execution (mocking, cache, parallel, live, timeout) is already
correctly modeled as an `execution` binding, applied via overlay/agent-spec —
not infra, not flavour.** The `ExecutionBinding` fragment is the answer to
the cache/mocking frontier question; nothing needs to move. What's broken is
that the *Flavour* schema also carries a redundant, competing `spec.mocking:
{enabled, mode}` (`flavour.schema.yaml:170-179`) and `spec.prefer_local`
(`:139-144`) that duplicate/shadow this. FT4 already lists removing both —
this doc confirms that's correct, not just cleanup.

## Where flavour and overlay actually converge — and why

Both `merge_agent_overlay` (`ctl/src/mas/ctl/overlay/merge.py:37`) and a
would-be flavour-application step patch a `spec` dict using the same
mental model (RFC 7396 merge-patch semantics, `apply_merge_patch` at
`merge.py:22`). The overlay schema even already declares `target.kind:
Flavour` as a legal selector (`overlay.schema.yaml:70-76`). But today that's
dead schema surface: `merge_overlay`'s dispatch
(`merge.py:325-349`) only special-cases `target.kind ∈ {mas, app, workflow}`;
anything else — including an explicit `Flavour` target — silently falls
through to `merge_agent_overlay`, which assumes an *agent* spec shape
(`tools`, `skills`, `memory`, `llm`, `plugins`, …). There is no
`merge_flavour_overlay`, and no call site anywhere invokes `merge_overlay`
against a loaded Flavour manifest — flavours are validated
(`ctl/src/mas/ctl/session/flavour.py:51`, `validate_flavour`, "applies
nothing") and then discarded.

**Resolution:** flavour and overlay are not actually converging on the same
concept — they converge on the same *mechanism* (JSON merge-patch over a
manifest's `spec`). That mechanism should be shared, not duplicated per
manifest kind. Concretely:

1. Overlay stays the **one** patch mechanism. `merge_overlay` gets a real
   `target_kind` dispatch table (`agent` → `merge_agent_overlay`, `mas/app/
   workflow` → `merge_mas_overlay`, `flavour` → a new
   `merge_flavour_overlay`) instead of an `if/else` that only recognizes two
   cases and silently defaults the rest to "agent."
2. `merge_flavour_overlay` is deliberately narrow: it only accepts the keys
   FT4 leaves in the slimmed Flavour schema (protocol/`agent_comm`,
   `observability` plugin list, `control` plugin list — deployment posture
   only). It reuses the generic list/dict merge logic already written for
   `observability` in `merge_agent_overlay` (`merge.py:156-175`) — that logic
   doesn't actually know or care whether the base spec is an agent or a
   flavour, so it should be extracted into a shared helper
   (`merge_plugin_list_field(base_spec, overlay_spec, key)`) called from both
   `merge_agent_overlay` and `merge_flavour_overlay`, rather than duplicated.
3. Flavours remain schema-validated-only for every field FT4 removes (llm
   inference params, skills, `prefer_local`, `mocking`) — those are agent-spec
   / execution concerns and a flavour overlay must not be able to reintroduce
   them through the back door. `merge_flavour_overlay` should reject unknown
   patch keys the same way `parse_execution` rejects unknown execution keys,
   rather than silently ignoring or (worse) applying them.

This also resolves the "can overlay express arbitrary plugin wiring?"
question from FT7: no, by design. The plugin-list fragments
(`observability-binding.schema.yaml`, `control-binding.schema.yaml`) are
closed enums with a couple of whitelisted config keys each
(`additionalProperties: false`), not a free-form plugin-config bag. An
overlay can select which known plugins run and set their few sanctioned
options (`path`/`events_file`, `output_path`/`otel_file`) — it cannot invent
a new plugin id or hand it arbitrary config. That's a feature, not a gap:
it's what "observability is a flavour concern, not agent logic" is supposed
to mean — you configure *which* plugins are wired, not *how* a plugin
works internally.

## The concrete evidence this frontier is currently confused

Observability today exists in three incompatible shapes, which is the
`BRANCHES.md` FT7 complaint made precise:

| Location | Shape | Consumed by runtime today? |
|---|---|---|
| `Flavour.spec.observability` (`flavour.schema.yaml:192-213`) | OTel span-export config (`backend: otel_sdk\|otel_extended\|none`, `output_path`, `otlp_endpoint_env`, `trace_content`) | No — `validate_flavour` never applies it |
| `library-standard/flavours/local-benchmark.yaml` (`observability: {backend: native, service_name: ...}`) | Neither of the other two shapes (`native` isn't in the documented enum; `service_name` is read nowhere) | No |
| `Overlay.spec.patch.observability` / Agent `spec.observability` (`observability-binding.schema.yaml`) | Plugin list (`[native, {otel: {...}}]`) | **Yes** — this is what `manifest_config.py:150` (`parse_observability`) actually reads |

Only the third shape is live. FT4's job is to delete the first two and make
the third the Flavour schema's shape too (`local` → `[native]`), so there is
one `observability` shape everywhere it appears, and it's overlay-patchable
by construction rather than needing a bespoke merge path.

## Summary table (the actual boundary)

| Concern | Owner | Mechanism |
|---|---|---|
| Endpoints, api keys, model wire-names, tool name→impl mapping | **Infra** (`infra/v1`: `InfraBundle`, `LLMProxy`, `ToolProvider`, …) | `--infra-ref` / workspace `infra_refs`, never overlay-patched |
| Protocol, observability/control plugin *selection* | **Flavour** | `--flavour NAME` (+ future flavour overlay, this doc §3) |
| LLM inference params, tools, skills, memory | **Agent spec / overlay** | `merge_agent_overlay`, `build_cli_overlay` |
| Mocking, cache, parallel/live/timeout | **Execution** (a binding within agent-spec/overlay, not its own manifest kind) | `spec.execution`, `ExecutionBinding` |

## What this unblocks

- **FT4**: strip `Flavour.spec.{llm-inference-params, skills, mocking,
  prefer_local}`; rework `observability`/`control` into the plugin-list
  shape; make flavour resolution *apply* (not just validate) the surviving
  fields.
- **FT7**: once FT4 lands, `--events*` becomes a `merge_flavour_overlay`
  patch (`spec.patch.observability`) built by `build_cli_overlay`-style code,
  applied to the resolved flavour spec, instead of overriding
  `agent_data.spec.observability` via `observability_config_from_manifest`.
  `--events-stdout` still needs an explicit decision: add `stdout` to
  `observability-binding.schema.yaml`, or keep it a pure ctl runtime toggle
  applied after binding resolution (it's arguably execution-time behavior,
  not deployment posture) — this doc doesn't resolve that one; it's a small
  follow-up call for whoever implements FT7.
