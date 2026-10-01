#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Third-party OTel stays off unless the user or the otel plugin opts in."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from mas.third_party_otel import A2A_SDK_OTEL_FLAG, pin_third_party_otel_off


def test_pin_defaults_a2a_sdk_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(A2A_SDK_OTEL_FLAG, raising=False)
    pin_third_party_otel_off()
    assert os.environ[A2A_SDK_OTEL_FLAG] == "false"


def test_pin_respects_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(A2A_SDK_OTEL_FLAG, "true")
    pin_third_party_otel_off()
    assert os.environ[A2A_SDK_OTEL_FLAG] == "true"


def test_registry_list_does_not_import_a2a_or_otel_sdk() -> None:
    env = dict(os.environ)
    env.pop(A2A_SDK_OTEL_FLAG, None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "from mas.runtime.registry import get_registry; "
            "get_registry().list(); "
            "mods = set(sys.modules); "
            "print('a2a' if 'a2a' in mods or any(m.startswith('a2a.') for m in mods) else 'no-a2a'); "
            "print('otel' if any(m == 'opentelemetry' or m.startswith('opentelemetry.') for m in mods) else 'no-otel'); "
            "print('a2a-plugin' if any(m.startswith('library_ioa.plugins.a2a.') and m != 'library_ioa.plugins.a2a' for m in mods) else 'no-a2a-plugin')",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    lines = result.stdout.strip().splitlines()
    assert lines == ["no-a2a", "no-otel", "no-a2a-plugin"], result.stdout + result.stderr


def test_importing_mas_runtime_pins_a2a_flag() -> None:
    env = dict(os.environ)
    env.pop(A2A_SDK_OTEL_FLAG, None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; import mas.runtime; "
            f"print(os.environ[{A2A_SDK_OTEL_FLAG!r}])",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    assert result.stdout.strip() == "false"
