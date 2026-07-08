<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-runtime — Documentation Hub

> **This is the public documentation hub for mas-runtime users & integrators.**

> **Public tutorials** live under [`docs/tutorials/`](../../docs/tutorials/) (`mas-ctl`, `mas-lab`).

---

| I want to… | Start here |
| --- | --- |
| Use `mas-runtime` for the first time | [README.md](../README.md) · [library-samples/apps/](../../library-samples/apps/) |
| Run interactively on host | [docs/tutorials/01-building-an-agent/](../../docs/tutorials/01-building-an-agent/README.md) (`mas-ctl chat`) |
| Integrate with LangChain / LangGraph / AutoGen | [architecture-instrumentation.md](architecture-instrumentation.md) |
| Implement a plugin | [plugin-and-tool-authoring.md](plugin-and-tool-authoring.md) → [contracts-reference.md](contracts-reference.md) |
| Enable CoT / ReAct / Reflection | [design-patterns.md](design-patterns.md) |
| Configure dev vs prod (flavours) | [plugin-flavours.md](plugin-flavours.md) |
| Understand plugin names, URNs, aliases, and discovery | [plugin-aliases.md](plugin-aliases.md) |
| Understand how plugin *types* get registered (manifests, fixpoint, library discovery) | [plugin-registry-manifests.md](plugin-registry-manifests.md) |
| Understand/override default model, design pattern, context manager | [agent-defaults.md](agent-defaults.md) |
| Understand the runtime architecture (Mealy product, Σ, chokepoints) | [automaton-product-model.md](automaton-product-model.md) |
| Debug Σ ordering and closure | [dev/contracts/mealy-hooks-and-closure.md](dev/contracts/mealy-hooks-and-closure.md) |

---

## User documentation

Guides for teams building agents with the runtime.

### Getting started

1. **Install**: `uv sync --package mas-runtime` (from repo root)
2. **Choose a runtime integration**:

- `mas-ctl chat` — recommended interactive path on host
- `mas-runtime run-agent` — headless Docker / CI
- LangGraph + runtime wrapper — graph workflows with kernel envelopes
- agent-remote SDK + runtime — multi-agent coordination

3. **Add plugins** — see [plugin-and-tool-authoring.md](plugin-and-tool-authoring.md)
4. **Configure a flavour** — see [plugin-flavours.md](plugin-flavours.md)

### Reference guides

| Document | Answers |
| --- | --- |
| [contracts-reference.md](contracts-reference.md) | Which contracts exist? Which do I implement for my use-case? |
| [plugin-and-tool-authoring.md](plugin-and-tool-authoring.md) | `@plugin` decorator, tool library, governance events, contract authoring |
| [plugin-flavours.md](plugin-flavours.md) | How to configure environment-specific settings (model, keys, log level) |
| [design-patterns.md](design-patterns.md) | How to enable CoT, ReAct, Reflection, Tree-of-Thoughts via overlay |
| [naming-standards.md](naming-standards.md) | Naming conventions for plugins, spans, tools, and manifests |

### Tutorials

See **[docs/tutorials/index.md](../../../docs/tutorials/index.md)** for the full learning path.

| # | Tutorial | Key concept |
| --- | --- | --- |
| 01 | [Building an agent](../../../docs/tutorials/01-building-an-agent/) | `mas-ctl chat` · overlays · tools/skills/memory |
| 02 | [Creating a MAS](../../../docs/tutorials/02-creating-a-mas/) | `mas-ctl run-mas` · topology overlays |
| 03 | [Experiments & analysis](../../../docs/tutorials/03-experiments-and-analysis/) | `mas-lab` telemetry · plots · benchmarks |

Also see **[Tutorial 01 — Building an agent](../../docs/tutorials/01-building-an-agent/README.md)** and
**[registry_manifest_demo.py](../examples/registry_manifest_demo.py)** for programmatic registry resolution.

### Common how-tos

| Task | Where |
| --- | --- |
| Wrap an existing LangChain app | [architecture-instrumentation.md](architecture-instrumentation.md) §1 |
| Add custom governance (budget, guardrails, HITL) | Overlays + `BudgetTracker` — see [contracts-reference.md](contracts-reference.md); sandbox/TBAC in mas-lab-internal |
| Emit custom OTel spans | `RecorderContract` + `SpanRecorder` — see [contracts-reference.md](contracts-reference.md) |
| Use tool-server / LlamaIndex tools | [architecture-instrumentation.md](architecture-instrumentation.md) §2 |

### FAQ

**Do I need LangChain or LangGraph?**
No. The default path is declarative manifests + `mas-ctl chat` / `SessionController`.

**How do I add custom governance logic?**
Register governance plugins on envelope chokepoints (σ₂, σ₆) or implement `ToolContract` guards.
See [production-path.md](production-path.md) and [contracts-reference.md](contracts-reference.md).

**What's the difference between agent-remote SDK and the runtime kernel?**
`agent-remote SDK` = multi-agent coordination and transport.
`RuntimeKernel` + `SessionController` = single-agent Mealy product execution with contracts and plugins.

**Can I use multiple frameworks side-by-side?**
Yes — plugins operate via contracts, not framework APIs.

---

## Developer documentation

For teams extending the runtime with custom plugins and contracts.

### Architecture & integration

| Document | For |
| --- | --- |
| [architecture-instrumentation.md](architecture-instrumentation.md) | Wrapping LangChain / LangGraph / AutoGen; Mealy machine in execution; agent-remote vs single-agent |
| [contracts-reference.md](contracts-reference.md) | Implementing custom contracts and plugins |
| [trajectory-schema.md](trajectory-schema.md) | OTel span format, trace hierarchy, logging agent execution |
| [plugin-and-tool-authoring.md](plugin-and-tool-authoring.md) | Writing plugins with the `@plugin` decorator; governance integration |

### Contract developer reference

Deep dive into how contracts work, how they interact, and how to extend them:

| Document | Purpose |
| --- | --- |
| [dev/contracts/index.md](dev/contracts/index.md) | Overview of all contract types with examples |
| [dev/contracts/taxonomy.md](dev/contracts/taxonomy.md) | Complete contract definitions and requirements |
| [dev/contracts/design-patterns.md](dev/contracts/design-patterns.md) | How contracts compose and interact in plugins |
| [dev/contracts/mealy-hooks-and-closure.md](dev/contracts/mealy-hooks-and-closure.md) | Execution model: 5-chokepoint Mealy machine, state transitions |
| [mealy-envelope.md](mealy-envelope.md) | Envelope hot path — what is wrapped, OSS tests |
| [automaton-product-model.md](automaton-product-model.md) | Full agent product ⊗ model |
| [dev/contracts/messaging-and-orchestration.md](dev/contracts/messaging-and-orchestration.md) | Agent communication patterns and orchestration protocols |
| [dev/contracts/execution-control-and-observability.md](dev/contracts/execution-control-and-observability.md) | Control flow, observability hooks, and event routing |
| [dev/contracts/model-and-tools.md](dev/contracts/model-and-tools.md) | LLM and tool contract details with lifecycle |

### Schema Specifications

Detailed schema documentation for declarative configuration files:

| Schema | File | Purpose |
| --- | --- | --- |
| [Agent Manifest](dev/schemas/agent-manifest.md) | `agent.yaml` | Agent configuration, LLM settings, plugins, tools |
| [MAS Topology](dev/schemas/mas-topology.md) | `topology.yaml` | Multi-agent system definition, agent coordination, policies |
| [Tool Definition](dev/schemas/tool-definition.md) | Tool schema | Tool implementation specification with input/output parameters |

### API Reference

Complete library API documentation for building agents and experiments:

| API | Document | For |
| --- | --- | --- |
| **mas-runtime** | [dev/api-reference/mas-runtime-api.md](dev/api-reference/mas-runtime-api.md) | Kernel, plugins, contracts, session bootstrap |
| **mas-lab** | [../../docs/libraries.md](../../docs/libraries.md) | Benchmarks, pipelines, controller |

### Command-Line Interface (CLI)

Complete reference for all CLI tools:

**[dev/cli/cli-reference.md](dev/cli/cli-reference.md)** covers:

- `mas-ctl` — Interactive chat, compose, validate, `run-mas`
- `mas-runtime` — Headless `run-agent` (containers)
- `mas-lab` — Experiment benchmarking and analysis

### Framework architecture (deep dives)

- [context-segmentation.md](context-segmentation.md) — context assembly and provenance
- [semantic-protocols.md](semantic-protocols.md) — URNs and governance scopes
- [dev/contracts/](dev/contracts/) — contract reference

### Contributing

Before submitting a PR to this repository:

1. Ensure your changes are **user-facing, integration-focused, or developer-reference**
2. **User docs**: tutorials, guides, integration examples, API reference
3. **Developer reference**: contract explanations, hook dispatch, execution model
4. **Internal/theoretical docs**: submit to a separate internal repository instead
5. Update `index.md` and cross-references if adding a new document
6. Test all links with `make check-links` (or equivalent in your environment)

---

- **Code examples**: Must be executable and tested.
