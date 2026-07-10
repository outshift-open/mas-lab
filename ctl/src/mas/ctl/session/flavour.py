#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Flavour selection + validation for the interactive commands (chat / tui / run-mas).

A *flavour* is a deployment posture — a ``kind: Flavour`` manifest bundled in
``mas-library-standard`` (``flavours/<name>.yaml``). It selects protocols and,
in a later pass, observability/control plugins. It is **not** a place for LLM
parameters (those live in the agent spec) or infra coordinates.

Only ``local`` is supported this release; the ``--flavour`` flag is a
forward-compatible, validated selector. This module resolves and *validates*
the chosen flavour — it deliberately applies nothing to the manifest yet. The
schema/semantics rework (stripping llm/skills/mocking, observability as plugin
selection) is tracked as FT4 in ``BRANCHES.md``.
"""

from __future__ import annotations

import contextlib
import importlib.resources
from typing import Any

import yaml

_FLAVOUR_PACKAGE = "mas.library.standard"
DEFAULT_FLAVOUR = "local"
# Flavours wired into the interactive path today. Others (mock, local-benchmark)
# exist in library-standard for benchmarks; offline chat uses the mock-llm overlay.
SUPPORTED_FLAVOURS = ("local",)


class FlavourError(ValueError):
    """Raised when a flavour name is unknown / unsupported, or its manifest is invalid."""


def _load_bundled_flavour(name: str) -> dict[str, Any]:
    """Load ``flavours/<name>.yaml`` from library-standard, or ``{}`` if absent."""
    resource = importlib.resources.files(_FLAVOUR_PACKAGE).joinpath("flavours", f"{name}.yaml")
    try:
        with contextlib.ExitStack() as stack:
            path = stack.enter_context(importlib.resources.as_file(resource))
            if not path.exists():
                return {}
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        # library-standard not installed (mas-ctl only hard-deps mas-runtime).
        return {}
    return data if isinstance(data, dict) else {}


def validate_flavour(name: str | None = None) -> None:
    """Resolve and schema-validate the selected flavour; apply nothing.

    Raises :class:`FlavourError` for an unknown/unsupported name or an invalid
    flavour manifest. Defaults to ``local``. A missing library-standard (so the
    bundled flavour can't be loaded) degrades to a no-op rather than breaking
    the run.
    """
    resolved = (name or DEFAULT_FLAVOUR).strip().lower()
    if resolved not in SUPPORTED_FLAVOURS:
        supported = ", ".join(SUPPORTED_FLAVOURS)
        raise FlavourError(
            f"flavour {resolved!r} is not supported yet (supported: {supported}). "
            f"For offline runs use `-o overlays/mock-llm.yaml`; "
            f"see all bundled flavours with `mas-ctl flavour list`."
        )
    data = _load_bundled_flavour(resolved)
    if not data:
        return

    from mas.ctl.validate import validate_data, validation_enabled

    if validation_enabled():
        result = validate_data(data, kind="flavour")
        try:
            result.raise_if_failed()
        except Exception as exc:  # normalise to a clean CLI error
            raise FlavourError(f"flavour {resolved!r} manifest is invalid: {exc}") from exc
