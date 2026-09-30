<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Flavour manifest (`kind: Flavour`)

**Package:** `mas-runtime` · **Schema:** `flavour.schema.yaml` · **apiVersion:** `flavour/v1` (or `mas/v1`)

A **flavour** is a deployment preset: **observability** export, transport, tool policy —
not model API URLs (those live in **infra** manifests and **agent** `models`).

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Sits between application manifests and infrastructure: deployment profile for protocol,
observability, tool policy, and RAG/skills backend.

---

## Two aspects (your model)

| Aspect | Flavour sections | Examples |
|--------|------------------|----------|
| **Control / observation** | `observability`, `telemetry`, `tools.exposure_protocol` | Native/OTel export; MCP exposure protocol |
| **Protocol / comm** | `agent_comm` | `protocol: local \| grpc \| hybrid`, `mode`, `emulation` |

Governance plugins that **alter trajectory** are usually declared on **Agent `plugins[]`** or
via **Overlay**; flavour configures the **runtime plane** they attach to.

---

## What does not belong here

| Forbidden in Flavour | Belongs in |
|---------------------|------------|
| `model`, `api_base` | Agent `models` + infra `LLMProxy` |
| `infra_refs` | `config.yaml`, env `MAS_INFRA_REFS`, CLI `--infra-ref` |

Enforced by `FlavourSeparationValidator` and `mas-lab check-config`.

---

## Selection at run time

Flavours select how this application exposes agents or tools. MCP consumption is
not a flavour concern: a `ToolServerRegistry` with `usage: use` is an infra
dependency. A local/MCP mix is expressed by infra dependencies, not flavour.

```bash
mas-ctl run-mas mas.yaml --infra-ref ./infra/prod-bundle.yaml
```

For benchmarks, select a flavour on the experiment or CLI:

```bash
mas-lab benchmark run experiment.yaml --flavour local
```

`metadata.default_flavour` on MAS provides the default name.

**OSS mas-lab:** canonical flavour YAML lives only under `library-standard/src/mas/library/standard/flavours/` (`local.yaml`, `mcp.yaml`, `local-benchmark.yaml`). The scheduler resolves flavours via `mas.lab.flavour.resolve.resolve_flavour_path()` — do not copy flavour YAML into individual labs or samples.

---

## See also

- [infra.md](infra.md)
- [experiment.md](experiment.md) — `default_flavour`
