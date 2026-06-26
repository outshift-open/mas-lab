#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# Reference entry point for running the controller HTTP API directly (PR #5).
# Prefer: mas-lab control start  or  mas-lab serve
from mas.lab.controller.fastapi_app import app  # noqa: F401
