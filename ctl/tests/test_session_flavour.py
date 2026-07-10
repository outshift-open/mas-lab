#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the chat/tui/run-mas flavour selector (mas.ctl.session.flavour).

Flavours are validate-only for now: resolve + schema-validate the selected
flavour manifest, apply nothing (see BRANCHES.md FT4).
"""

from __future__ import annotations

import pytest

from mas.ctl.session import flavour as flavour_mod
from mas.ctl.session.flavour import DEFAULT_FLAVOUR, FlavourError, validate_flavour


def test_default_flavour_is_local() -> None:
    assert DEFAULT_FLAVOUR == "local"


def test_validate_local_ok() -> None:
    validate_flavour("local")  # bundled + valid -> no raise


def test_validate_none_defaults_to_local() -> None:
    validate_flavour(None)


def test_validate_is_case_insensitive() -> None:
    validate_flavour("LOCAL")


def test_unsupported_flavour_raises_with_guidance() -> None:
    with pytest.raises(FlavourError) as exc:
        validate_flavour("prod")
    msg = str(exc.value)
    assert "not supported" in msg and "local" in msg
    assert "mock-llm" in msg  # points offline users to the overlay


def test_missing_library_degrades_to_noop(monkeypatch) -> None:
    # If the bundled flavour can't be loaded (library-standard absent), a
    # supported name is a no-op rather than a hard failure.
    monkeypatch.setattr(flavour_mod, "_load_bundled_flavour", lambda name: {})
    validate_flavour("local")


def test_invalid_manifest_raises_flavour_error(monkeypatch) -> None:
    monkeypatch.setattr(
        flavour_mod, "_load_bundled_flavour", lambda name: {"kind": "Flavour", "spec": {}}
    )

    class _Result:
        def raise_if_failed(self):
            raise ValueError("bad manifest")

    monkeypatch.setattr("mas.ctl.validate.validation_enabled", lambda: True)
    monkeypatch.setattr("mas.ctl.validate.validate_data", lambda data, kind: _Result())
    with pytest.raises(FlavourError, match="manifest is invalid"):
        validate_flavour("local")
