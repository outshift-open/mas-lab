from __future__ import annotations

import sys
from pathlib import Path

COMPLIANCE_ROOT = Path(__file__).resolve().parents[2] / "compliance" / "mcp"
sys.path.insert(0, str(COMPLIANCE_ROOT))
