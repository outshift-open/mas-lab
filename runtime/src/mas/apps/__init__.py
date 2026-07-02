#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.apps — discover sample apps from manifest library roots."""

from __future__ import annotations

from ._registry import AppNotFoundError, get_app, list_apps, resolve_app_manifest

__all__ = ["get_app", "list_apps", "AppNotFoundError", "resolve_app_manifest"]
