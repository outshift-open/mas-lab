#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Backward-compatible re-exports — prefer the registry-backed observability plugins."""

from mas.ctl.adapters.obs.factory import DEFAULT_OTLP_ENDPOINT, DEFAULT_OTLP_ENDPOINT_ENV  # noqa: F401
from mas.ctl.manifest.spec_bindings import resolve_manifest_cfg_value as resolve_env_value  # noqa: F401

__all__ = ["DEFAULT_OTLP_ENDPOINT", "DEFAULT_OTLP_ENDPOINT_ENV", "resolve_env_value"]
