#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from library_ioa import package_root
from library_ioa.plugins.mcp import MCPClientFactory, MCPProviderSpec, MCPToolProvider
from mas.runtime.registry import get_registry


def test_package_root_finds_library_yaml() -> None:
    root = package_root()
    assert (root / "library.yaml").is_file()


def test_plugin_package_exports() -> None:
    assert MCPToolProvider is not None
    assert MCPClientFactory is not None
    assert MCPProviderSpec is not None


def test_urn_registry_resolves_mcp_shortcut() -> None:
    info = get_registry().resolve_by_type("tool_provider", "mcp")
    assert info is not None
    assert info.load_class() is MCPToolProvider
