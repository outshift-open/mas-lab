<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Instrumentation Tools

This folder documents instrumentation utilities used to observe MAS traffic.

## OSS

Shipped observability in v2 uses native event recording (`events.jsonl`) and optional
OpenTelemetry export via manifest `observability` config — see
[architecture-instrumentation.md](../architecture-instrumentation.md).

The following MITM-style proxy docs are **reference only**; running them is **not**
part of the open-source release (see org-level `outshift-open/ROADMAP.md` non-goals).

## Not in OSS (do not expect these paths in the repo)

| Topic | Status |
| --- | --- |
| agent-remote MITM | Internal / removed from OSS tree |
| tool-server MITM | Internal / removed from OSS tree |
| agent-remote protocol | Not shipped in OSS |
| tool-server protocol | Not shipped in OSS |
| observe-sdk plugin aliases | Internal only |

For cognitive fault injection (MITM plugin), see internal `mas-lab-internal` — not in this repository.

## Related

- [Plugins and agent composition](../plugins/agent_plugins.md) (if present)
- [mealy-envelope.md](../mealy-envelope.md) — native span emission on envelope symbols
