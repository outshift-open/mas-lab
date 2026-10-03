#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.spec.runtime_plugins import (
    attach_runtime_plugins,
    debug_script_wanted,
    peel_legacy_debug_script,
)


def test_peel_moves_governance_debug_script_to_spec_debug() -> None:
    spec = {
        "governance": [
            "sample",
            {"debug_script": {"script_file": "./debug.gdb"}},
        ]
    }
    peel_legacy_debug_script(spec)
    assert spec["governance"] == ["sample"]
    assert spec["debug"] == {"script_file": "./debug.gdb"}


def test_debug_script_wanted_from_spec_or_config_refs() -> None:
    assert debug_script_wanted({}, []) is False
    assert debug_script_wanted({"debug": {}}, []) is True
    assert debug_script_wanted({}, ["mas.runtime.debug_script"]) is True
    assert debug_script_wanted({}, ["gdb"]) is True


def test_attach_puts_debug_script_on_runtime_plugins_not_gov() -> None:
    cfg = attach_runtime_plugins(
        KernelConfig(),
        {"debug": {"script": "break tool_call calc\n"}},
        enabled_refs=[],
    )
    assert len(cfg.runtime_plugins) == 1
    plugin = cfg.runtime_plugins[0]
    assert plugin.plugin_id == "debug_script@v1"
    assert cfg.egress_governance_plugin is None


def test_attach_skips_when_not_enabled() -> None:
    cfg = attach_runtime_plugins(KernelConfig(), {}, enabled_refs=[])
    assert cfg.runtime_plugins == ()


def test_attach_skips_when_registry_has_no_debug_script(monkeypatch) -> None:
    cfg = KernelConfig()

    class _Empty:
        def resolve_by_type(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("mas.runtime.registry.get_registry", lambda: _Empty())
    cfg = attach_runtime_plugins(
        cfg,
        {"debug": {"script": "break tool_call calc\n"}},
        enabled_refs=[],
    )
    assert cfg.runtime_plugins == ()
