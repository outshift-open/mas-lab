<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Sample workspace

Canonical `config.yaml` for OSS development and CI.

**Use it**

- Copy `config.yaml` to your project root, or
- `export MAS_WORKSPACE_ROOT=/path/to/mas-lab/library-samples/sample-workspace`

**Defaults**

- Inherit user `default_infra` (Tutorial 0) — requires an API key for live runs
- Offline CI: pair `standard:openai` with llm_cache replay (`raise_on_miss`)
- Local ctl/lab flavours for benchmarks and tutorials

For live OpenAI/production infra, start from
[`docs/tutorials/00-environment-setup/config.openai.example.yaml`](../../docs/tutorials/00-environment-setup/config.openai.example.yaml).

Schema: [`docs/schemas/config.schema.yaml`](../../docs/schemas/config.schema.yaml).
