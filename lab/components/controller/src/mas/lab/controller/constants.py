#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared constants for the FastAPI controller API."""

from __future__ import annotations

import os
from pathlib import Path

from mas.runtime.xdg import mas_cache_root, mas_data_root

LIBRARIES_DIR = Path(
    os.getenv(
        "MAS_LIBRARIES_DIR",
        str(Path.home() / "mas-lab"),
    )
)

MAX_TIMEOUT = 10800

MAS_LAB_ROOT = Path(os.environ.get("MAS_LAB_ROOT", mas_data_root()))

WEB_SEARCH_CACHE_DIR = mas_cache_root() / "web_search"

HIDDEN_FILES = {".DS_Store", ".run_ref", ".gitkeep"}

IOC_REPO = Path(os.environ.get("IOC_REPO", "")) if os.environ.get("IOC_REPO") else None

MAS_LAB_OSS = Path(os.environ.get("MAS_LAB_OSS", "")) if os.environ.get("MAS_LAB_OSS") else None
CLARIS_LIB = Path(os.environ.get("CLARIS_LIB", "")) if os.environ.get("CLARIS_LIB") else None
EVALUATOR_ENV = os.environ.get("EVALUATOR_ENV") or None
MAS_CTL_MODEL = os.environ.get("MAS_CTL_MODEL") or None

IOC_RUNS_ROOT = MAS_LAB_ROOT / "ioc-runs"
IOC_RUN_TIMEOUT = int(os.environ.get("IOC_RUN_TIMEOUT", "3600"))

SCHEMAS_DIR = Path(__file__).parent / "schemas"
PIPELINE_STEP_TYPES_PRE_PATH = SCHEMAS_DIR / "pipeline-step-types-pre.json"
PIPELINE_STEP_TYPES_POST_PATH = SCHEMAS_DIR / "pipeline-step-types-post.json"
