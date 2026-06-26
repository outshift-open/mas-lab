<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Golden-run fixtures — events.jsonl + trace-cache backup for CI parity.

Regenerate after intentional trace changes:

```bash
# Default lab-smoke fixture
python scripts/capture_golden_run.py

# One or more labs (manifest label, experiment path, or *.lab directory)
python scripts/capture_golden_run.py --labs design-space
python scripts/capture_golden_run.py --labs all
```

Manifest: `labs.yaml` (label → experiment path).

Files per label (e.g. `lab-smoke/`):

- `events.jsonl` — raw trace from mock-LLM single run
- `events.normalized.jsonl` — timestamps/ids stripped for diff
- `events.sha256` — fingerprint of normalized events
- `cache-backup/<label>/` — full trace-cache entry copy + manifest
