<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Local OTel collector and ClickHouse

```bash
docker compose -f library-telemetry/docker/compose.yaml up -d
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export CLICKHOUSE_HOST=localhost
```

`$OTEL_EXPORTER_OTLP_ENDPOINT` is a shortcut for `infra/local-otel.yaml`.
`$CLICKHOUSE_HOST` is a shortcut for `infra/local-clickhouse.yaml`.

Images: `otel/opentelemetry-collector-contrib` and `clickhouse/clickhouse-server`.
The collector config is `otel-collector.yaml` in this directory (OTLP HTTP `:4318`
plus ClickHouse `otel_traces`). Used from [Tutorial 8 — Telemetry](../../docs/tutorials/08-telemetry/README.md).
