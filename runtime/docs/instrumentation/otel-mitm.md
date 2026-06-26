<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# OTel MITM (internal)

OTel/LLM MITM proxy processes live in **`mas-lab-internal/tools/mitm/`**.

OSS observability uses the **native** plugin (`events.jsonl` traces). Extended OTel
span export (`otel_sdk`, `otel_extended`, KG/ontology pipelines) lives in
**`mas-lab-internal`**.

## Related

- [Instrumentation tools](index.md)
This tool is not part of the open-source release. See `runtime/docs/plugins/mitm-plugin.md`.
