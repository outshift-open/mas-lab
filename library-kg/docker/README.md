<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Local OXP / Neo4j for Tutorial 8

MAS-Lab Tutorial 8 (KG & OXP) serializes knowledge graphs in two ways:

| Store | How | This package |
| --- | --- | --- |
| `kg.json` / `kg.jsonld` on disk | `normalize_events` / `normalize_otel` | always |
| Neo4j | `neo4j_push` + `infra/local-neo4j.yaml` | `[neo4j]` extra |

```bash
docker compose -f library-kg/docker/compose.yaml up -d
export NEO4J_URI=bolt://localhost:7687   # shortcut for infra/local-neo4j.yaml
```

`$NEO4J_URI` is equivalent to passing `--infra library-kg/infra/local-neo4j.yaml`.

The Observe-and-Explain Platform (OXP) `norm.normalize()` path that Tutorial 8
uses for **OTel → KG** does not need this compose — it is an in-process Python
call (`mas-library-kg[norm]`). Bring up the full OXP stack (API, workers, UI)
from the OSS repo when you want the product UI, not for the tutorial pipelines:

https://github.com/outshift-open/observe-and-explain-platform/blob/main/backend/docker-compose.yml

ClickHouse that OXP can ingest from is owned by `mas-library-telemetry`
(`library-telemetry/docker/compose.yaml`, `$CLICKHOUSE_HOST`).
