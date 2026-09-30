<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
---
name: data-access-protocol
description: >
  MANDATORY prerequisite for get_metrics, get_logs, get_service_health,
  get_deployments, and query_db. Call activate_skill("data-access-protocol")
  before any of those tools.
---
# Data Access Protocol

When calling any data tool (`get_metrics`, `get_logs`, `get_service_health`,
`get_deployments`, `query_db`), you MUST pass the canonical service name as
the `service` argument.

Correct pattern:

```
get_metrics(service="payment-service")
get_logs(service="payment-service")
get_deployments(service="payment-service")
```

This text is why a model may name `get_deployments` even when that function
is not in the current LLM call's `tools` list. `gov_no_undeclared_tool`
BLOCKs that call.
