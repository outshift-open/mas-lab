<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Infrastructure manifests (`apiVersion: infra/v1`)

**Package:** `mas-runtime` · **Models:** `mas.runtime.manifest.infra_manifest`

**Infra** manifests declare resources the runtime resolves at execution time: LLM proxy
URLs, tool registries, secrets env mapping, OTel endpoints. Referenced from **MAS**
`infra_refs`, workspace config, or CLI `--infra-ref` — not from **overlay** business logic.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Provides resources: LLM endpoints, tool registries, tool servers, secrets mapping, optional
application service URLs, OTel/collector endpoints.

**Schema:** `infra.schema.yaml` (also validated via Python models in `infra_manifest.py`).

---

## Kinds

| `kind` | Purpose |
|--------|---------|
| `InfraBundle` | Compose other infra files (`spec.includes[]`); recursive merge |
| `LLMProxy` | OpenAI-compatible proxy URL, model catalogue, defaults |
| `LLMLocal` | Local inference (e.g. Ollama) |
| `ToolRegistry` | Map logical tool-set ids → JSON tool index paths |
| `ToolServerRegistry` | tool server ids and transport |
| `PersonalSecrets` | Logical token id → env var (gitignored) |
| `Application` | Named service endpoints |
| `Infrastructure` | Legacy alias |

---

## Bundles

```yaml
apiVersion: infra/v1
kind: InfraBundle
metadata:
  name: dev-stack
spec:
  includes:
    - llm-proxy.yaml
    - otel-collector.yaml
    - tool-registry.yaml
```

Referenced from MAS `spec.infra_refs`, workspace, or CLI `--infra-ref`.

---

## Separation from Flavour

| Infra | Flavour |
|-------|---------|
| **Where** (URLs, keys env names, registry paths) | **How** (protocol, OTel backend choice, tool-server policy) |
| Shared across flavours | Selected per deployment profile |

---

## See also

- [Flavour manifest](flavour.md)
- [user-config.md](../user-config.md) — workspace and `infra_refs`
- Source: `runtime/src/mas/runtime/manifest/infra_manifest.py`
