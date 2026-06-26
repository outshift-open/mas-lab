<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Sample workspace

Canonical `mas-workspace.yaml` for OSS development and CI.

**Use it**

- Copy `mas-workspace.yaml` to your project root, or
- `export MAS_WORKSPACE_ROOT=/path/to/mas-lab/examples/sample-workspace`

**Defaults**

- Mock LLM (`standard:mock-llm`) — no API key required
- Local ctl/lab flavours for benchmarks and tutorials

For live OpenAI/production infra, start from
[`docs/tutorials/00-environment-setup/mas-workspace.openai.example.yaml`](../../docs/tutorials/00-environment-setup/mas-workspace.openai.example.yaml).

Schema: [`docs/schemas/mas-workspace.schema.yaml`](../../docs/schemas/mas-workspace.schema.yaml).
