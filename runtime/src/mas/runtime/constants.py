#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Canonical identifiers and filenames — single source of truth for renames."""

from __future__ import annotations

# Workspace / user YAML config (same basename; different directories via xdg.py).
WORKSPACE_CONFIG_FILENAME = "config.yaml"
USER_CONFIG_FILENAME = WORKSPACE_CONFIG_FILENAME

# Former project config name — not read; kept for tests and migration docs only.
LEGACY_WORKSPACE_CONFIG_FILENAME = "mas-workspace.yaml"

CONNECTIONS_CONFIG_FILENAME = "connections.yaml"

# Kernel backend id (must match component-registry.yaml).
DEFAULT_RUNTIME_ID = "mas-runtime-py"
