<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Runtime engine manifests (`kind: RuntimeEngine`)

Shared kernel and LLM engine tuning for a deployment — queue depth, dispatch
step budget, streaming, and **LLM response cache policy** (read/write flags).
LLM endpoints are not configured here — use workspace `infra_refs` with
`standard:openai` (or another provider bundle). Offline CI uses
[llm_cache replay](llm-cache.md) recorded against a live provider.

**Agent and MAS manifests must not reference runtime** (no `runtime_refs` on
agents or MAS).

**Schema:** `docs/schemas/runtime/fragments/runtime-engine.schema.yaml`  
**Bundled ref:** `standard:runtime-default` (`library-standard`)

## Example

```yaml
apiVersion: infra/v1
kind: RuntimeEngine
metadata:
  name: ci-runtime
spec:
  engine:
    queue_depth: 64
    max_auto_steps: 256
  stream: false
  cache:
    read: true
    write: true
```

## How refs are resolved

Same discovery model as LLM infra, but **only** from deployment config — never
from agent, MAS, overlay, or flavour manifests:

`runtime_refs` is the parallel of `infra_refs` — same *kind* of wiring, different
manifest kind (`RuntimeEngine` vs `LLMProxy` / bundles):

| Source | Infra (`infra_refs`) | Runtime (`runtime_refs`) |
|--------|----------------------|---------------------------|
| CLI | `--infra-ref` | `--runtime-ref` |
| Environment | `MAS_INFRA_REFS` | `MAS_RUNTIME_REFS` |
| Workspace | `config.yaml` → `infra_refs` | `config.yaml` → `runtime_refs` |
| User default | `default_infra` in `~/.config/mas/config.yaml` | `default_runtime` in same file |
| Search dirs | `infra/`, `~/.config/mas/infra/` | `runtime/`, `~/.config/mas/runtime/` |

Example workspace file (see `library-samples/sample-workspace/config.yaml`):

```yaml
infra_refs:
  - standard:openai
runtime_refs:
  - standard:runtime-default   # optional; omit for package defaults only
```

Omit `runtime_refs` entirely to use package kernel/cache/stream defaults only.

`RuntimeEngine` manifests listed in **`infra_refs` are rejected** — use
`runtime_refs` or `--runtime-ref` instead.

## Precedence

When building `KernelConfig` and LLM cache/stream behaviour:

1. Package defaults (`DEFAULT_ENGINE_QUEUE_DEPTH`, etc.)
2. Merged `RuntimeEngine` manifest(s) from the resolution ladder above
3. CLI flags on `mas-ctl chat` (`--cache-read`, `--stream`, etc.)

## See also

- [Infrastructure manifests](infra.md) — LLM proxy and middleware (`infra_refs`)
- [user-config.md](../user-config.md) — workspace and XDG layout
- [LLM cache](llm-cache.md) — cache middleware vs cache policy
