#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stage overlay ``spec.params`` for tools without polluting the project tree."""

from __future__ import annotations

import os
import tempfile
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import yaml

MAS_RUNTIME_ARTIFACTS_ENV = "MAS_RUNTIME_ARTIFACTS_DIR"


def stage_runtime_params(
    params: dict[str, Any],
    *,
    environ: MutableMapping[str, str] | None = None,
) -> Path | None:
    """Write params to a process-scoped runtime dir and expose via ``MAS_RUNTIME_ARTIFACTS_DIR``.

    Writes ``artifacts/scene.yaml`` under ``$XDG_RUNTIME_DIR/mas-ctl/run-<pid>`` (or temp).
  Tool modules that read fixture paths from the filesystem should use that env var until
    they consume ``ctx.runtime_params`` from the engine tool loop.
    """
    if not params:
        return None

    env = os.environ if environ is None else environ
    base = env.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    root = Path(base) / "mas-ctl" / f"run-{os.getpid()}"
    sidecar_dir = root / "artifacts"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = sidecar_dir / "scene.yaml"
    sidecar_path.write_text(
        yaml.safe_dump(params, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    env[MAS_RUNTIME_ARTIFACTS_ENV] = str(root)
    return sidecar_path


def apply_runtime_params_to_instance(params: dict[str, Any], instance: Any) -> None:
    """Thread overlay params through the runtime ctx for in-process tool modules."""
    if not params:
        return
    ctx = getattr(getattr(instance, "driver", None), "ctx", None)
    if ctx is None:
        return
    # TODO: tool execution should read ctx.runtime_params; env sidecar is interim.
    ctx.runtime_params = dict(params)


def params_from_mas_config(mas_config: dict[str, Any]) -> dict[str, Any]:
    spec = mas_config.get("spec", mas_config) if isinstance(mas_config, dict) else {}
    raw = spec.get("params") or {}
    return dict(raw) if isinstance(raw, dict) else {}
