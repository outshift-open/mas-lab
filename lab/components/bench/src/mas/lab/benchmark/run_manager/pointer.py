#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Last-run pointer file helpers."""

import json
from pathlib import Path

# Pointer file written on every run start so `show last` always works,
# even for MAS experiments whose output_dir lives outside benchmarks_root.
_LAST_RUN_FILE = Path.home() / ".mas-lab" / ".last-run.json"
