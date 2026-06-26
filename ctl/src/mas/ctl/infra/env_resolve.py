#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve ``env:VAR`` indirections in infra/v1 manifests (k8s secretKeyRef style).

Infra manifests are committed without secrets. Deploy-time values (``api_base``,
URLs, feature flags) may reference process environment variables injected by
Kubernetes ``valueFrom``, Vault agents, or local ``.env`` files.

Syntax (same as ``mas.lab.connections``)::

    api_base: env:LLM_PROXY_API_BASE|https://llm-proxy.example/v1

    # required — empty string when unset (no default)
    uri: env:NEO4J_URI

Fields whose key ends in ``_env`` (``api_key_env``, ``password_env``, …) are
**secretKeyRef names** and are never resolved — the value is the env var name
that holds the secret, not an ``env:`` lookup.
"""

from __future__ import annotations

import os
from typing import Any

_ENV_PREFIX = "env:"
_SECRET_KEY_SUFFIX = "_env"


def resolve_env_string(value: str) -> str:
    """Expand ``env:VAR`` or ``env:VAR|default`` to a string."""
    if not value.startswith(_ENV_PREFIX):
        return value
    rest = value[len(_ENV_PREFIX) :].strip()
    if not rest:
        return ""
    if "|" in rest:
        var, default = rest.split("|", 1)
        var, default = var.strip(), default.strip()
    else:
        var, default = rest, ""
    if not var:
        return default
    return os.environ.get(var) or default


def resolve_manifest_values(data: Any) -> Any:
    """Recursively resolve ``env:`` strings in a parsed manifest mapping."""
    if isinstance(data, dict):
        return {k: _resolve_field(k, v) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_manifest_values(item) for item in data]
    if isinstance(data, str):
        return resolve_env_string(data)
    return data


def _resolve_field(key: str, value: Any) -> Any:
    if key.endswith(_SECRET_KEY_SUFFIX):
        return value if not isinstance(value, str) else str(value)
    return resolve_manifest_values(value)
