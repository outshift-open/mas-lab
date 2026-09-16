#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tool-provider registry routing. Provider kinds are library plugins, not runtime types."""

from __future__ import annotations

import pytest
from mas.library.standard.plugins.tools.local import LocalToolClaim, LocalToolProvider
from mas.runtime.registry.tool_provider_registry import (
    ToolProviderRegistry,
    provider_origin,
    providers_from_manifest,
)


def test_omitted_providers_binds_default_local():
    providers = providers_from_manifest({"spec": {}})
    assert len(providers) == 1
    assert isinstance(providers[0], LocalToolProvider)
    assert provider_origin(providers[0]) == "local"
    assert providers[0].implicit is True


def test_explicit_local_provider_from_spec():
    providers = providers_from_manifest(
        {
            "spec": {
                "providers": [
                    {"kind": "local", "name": "in-process", "tools": ["calc"]},
                ]
            }
        }
    )
    assert len(providers) == 1
    claim = providers[0]
    assert isinstance(claim, LocalToolProvider)
    assert claim.provider_name == "in-process"
    assert claim.tools_claim == ("calc",)
    assert claim.origin == "local"
    assert claim.implicit is False


def test_star_claim_replaces_local_same_name_keeps_other_local():
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider

    class _Local:
        def __init__(self, name):
            self._name = name

        def on_collect_tools(self, **_):
            return [{"name": self._name, "description": f"local-{self._name}"}]

        def on_execute_tool(self, name, args, **_):
            return {"source": "local", "name": name}

    class _Remote:
        provider_name = "search-remote"
        tools_claim = "*"
        origin = "external"

        def has_tools(self):
            return True

        def discover_tools(self, *, ctx=None):
            return [{"name": "web-search", "description": "remote-web-search"}]

        def list_tools(self, *, ctx=None):
            return self.discover_tools(ctx=ctx)

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"source": "remote", "name": tool_name}

    provider = ManifestToolProvider(overlay_providers=[_Remote(), LocalToolClaim()])
    provider._add_instance(_Local("web-search"), {"name": "web-search"})
    provider._add_instance(_Local("calc"), {"name": "calc"})
    tools = {t["name"]: t for t in provider.list_tools()}
    assert tools["web-search"]["description"] == "remote-web-search"
    assert tools["calc"]["description"] == "local-calc"
    assert provider.call_tool("web-search", {}) == {"source": "remote", "name": "web-search"}
    assert provider.call_tool("calc", {}) == {"source": "local", "name": "calc"}


def test_without_local_overlay_errors_on_unclaimed_spec_tool():
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider
    from mas.runtime.engine.tool_routing import UnclaimedToolError

    class _Local:
        def on_collect_tools(self, **_):
            return [{"name": "calc", "description": "local-calc"}]

        def on_execute_tool(self, name, args, **_):
            return {"source": "local"}

    class _Remote:
        provider_name = "search-remote"
        tools_claim = "*"
        origin = "external"

        def discover_tools(self, *, ctx=None):
            return [{"name": "web-search", "description": "remote-web-search"}]

        def list_tools(self, *, ctx=None):
            return self.discover_tools(ctx=ctx)

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"source": "remote"}

    provider = ManifestToolProvider(overlay_providers=[_Remote()])
    provider._add_instance(_Local(), {"name": "calc"})
    with pytest.raises(UnclaimedToolError, match="calc"):
        provider.list_tools()


def test_explicit_tools_list_does_not_steal_unlisted_local():
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider

    class _Local:
        def on_collect_tools(self, **_):
            return [{"name": "web-search", "description": "local"}]

        def on_execute_tool(self, name, args, **_):
            return {"source": "local"}

    class _Remote:
        provider_name = "search-remote"
        tools_claim = ("other-tool",)
        origin = "external"

        def discover_tools(self, *, ctx=None):
            return [
                {"name": "web-search", "description": "remote-web-search"},
                {"name": "other-tool", "description": "remote-other"},
            ]

        def list_tools(self, *, ctx=None):
            return [s for s in self.discover_tools() if s["name"] == "other-tool"]

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"source": "remote"}

    provider = ManifestToolProvider(overlay_providers=[_Remote(), LocalToolClaim(tools_claim=("web-search",))])
    provider._add_instance(_Local(), {"name": "web-search"})
    tools = {t["name"]: t for t in provider.list_tools()}
    assert tools["web-search"]["description"] == "local"
    assert tools["other-tool"]["description"] == "remote-other"
    assert provider.call_tool("web-search", {}) == {"source": "local"}


def test_discovery_failure_does_not_fall_back_to_local():
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider

    class _Local:
        def on_collect_tools(self, **_):
            return [{"name": "web-search"}]

        def on_execute_tool(self, name, args, **_):
            return {"source": "local"}

    class _Remote:
        provider_name = "search-remote"
        tools_claim = "*"
        origin = "external"

        def discover_tools(self, *, ctx=None):
            raise ConnectionError("remote down")

        def list_tools(self, *, ctx=None):
            return self.discover_tools(ctx=ctx)

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"source": "remote"}

    provider = ManifestToolProvider(overlay_providers=[_Remote(), LocalToolClaim()])
    provider._add_instance(_Local(), {"name": "web-search"})
    with pytest.raises(RuntimeError, match="discovery failed"):
        provider.list_tools()


def test_star_claim_queries_discover_before_routing():
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider

    class _Local:
        def on_collect_tools(self, **_):
            return [
                {"name": "web-search", "description": "local-web"},
                {"name": "calc", "description": "local-calc"},
            ]

        def on_execute_tool(self, name, args, **_):
            return {"source": "local", "name": name}

    class _Ext:
        provider_name = "search"
        tools_claim = "*"
        origin = "external"

        def __init__(self):
            self.discover_calls = 0

        def discover_tools(self, *, ctx=None):
            self.discover_calls += 1
            return [{"name": "web-search", "description": "remote"}]

        def list_tools(self, *, ctx=None):
            return [{"name": "web-search", "description": "remote"}]

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"source": "remote"}

    ext = _Ext()
    provider = ManifestToolProvider(overlay_providers=[ext, LocalToolClaim()])
    provider._add_instance(_Local(), None)
    assert provider.call_tool("web-search", {}) == {"source": "remote"}
    assert ext.discover_calls >= 1


def test_explicit_claim_does_not_query_discover_for_routing():
    from mas.runtime.engine.manifest_tool_provider import ManifestToolProvider

    class _Local:
        def on_collect_tools(self, **_):
            return [
                {"name": "web-search", "description": "local-web"},
                {"name": "calc", "description": "local-calc"},
            ]

        def on_execute_tool(self, name, args, **_):
            return {"source": "local", "name": name}

    class _Ext:
        provider_name = "search"
        tools_claim = ("web-search",)
        origin = "external"

        def discover_tools(self, *, ctx=None):
            raise AssertionError("explicit tools: [name] must not discover before routing")

        def list_tools(self, *, ctx=None):
            return [{"name": "web-search", "description": "remote"}]

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"source": "remote"}

    provider = ManifestToolProvider(overlay_providers=[_Ext(), LocalToolClaim()])
    provider._add_instance(_Local(), None)
    assert provider.call_tool("web-search", {}) == {"source": "remote"}
    assert provider.call_tool("calc", {}) == {"source": "local", "name": "calc"}


def test_registry_register_does_not_discover():
    class _Star:
        provider_name = "search"
        tools_claim = "*"
        origin = "external"
        discover_calls = 0

        def has_tools(self):
            return True

        def discover_tools(self, *, ctx=None):
            self.discover_calls += 1
            return [{"name": "web-search"}]

        def list_tools(self, *, ctx=None):
            return self.discover_tools(ctx=ctx)

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {"ok": True}

    registry = ToolProviderRegistry()
    star = _Star()
    registry.register_provider(star)
    assert star.discover_calls == 0
    registry.initialize()
    assert star.discover_calls == 1
    assert registry.call_tool("web-search", {}) == {"ok": True}


def test_registry_explicit_missing_name_raises_at_init():
    from mas.runtime.engine.tool_routing import ExplicitToolUnavailableError

    class _Named:
        provider_name = "search"
        tools_claim = ("web-search",)
        origin = "external"

        def discover_tools(self, *, ctx=None):
            raise AssertionError("explicit claim must not discover")

        def list_tools(self, *, ctx=None):
            return [{"name": "other-tool"}]

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {}

    registry = ToolProviderRegistry()
    registry.register_provider(_Named())
    with pytest.raises(ExplicitToolUnavailableError, match="web-search"):
        registry.initialize()


def test_apply_tool_server_defaults_fills_unset_connection_fields():
    from mas.runtime.registry.tool_provider_registry import apply_tool_server_defaults

    servers = [
        {
            "id": "localhost-mcp-tools",
            "transport": "streamable-http",
            "url": "http://127.0.0.1:9001/mcp",
            "timeout": 30,
            "follow_pagination": True,
            "cache_scope": "private",
            "headers": {"Authorization": "env:MCP_AUTH_HEADER"},
        }
    ]
    filled = apply_tool_server_defaults(
        {"name": "localhost-mcp-tools", "kind": "mcp", "tools": "*"},
        servers,
    )
    assert filled["url"] == "http://127.0.0.1:9001/mcp"
    assert filled["timeout"] == 30
    assert filled["follow_pagination"] is True
    assert filled["headers"] == {"Authorization": "env:MCP_AUTH_HEADER"}


def test_apply_tool_server_defaults_keeps_inlined_overlay_url():
    from mas.runtime.registry.tool_provider_registry import apply_tool_server_defaults

    filled = apply_tool_server_defaults(
        {
            "name": "localhost-mcp-tools",
            "kind": "mcp",
            "url": "http://127.0.0.1:9001/mcp",
            "timeout": 5,
        },
        [
            {
                "id": "localhost-mcp-tools",
                "url": "http://example.invalid/mcp",
                "timeout": 30,
                "follow_pagination": True,
            }
        ],
    )
    assert filled["url"] == "http://127.0.0.1:9001/mcp"
    assert filled["timeout"] == 5
    assert filled["follow_pagination"] is True


def test_apply_tool_server_defaults_keeps_explicit_false_pagination():
    from mas.runtime.registry.tool_provider_registry import apply_tool_server_defaults

    filled = apply_tool_server_defaults(
        {"name": "s", "kind": "mcp", "follow_pagination": False},
        [{"id": "s", "follow_pagination": True, "url": "http://127.0.0.1:9/mcp"}],
    )
    assert filled["follow_pagination"] is False
    assert filled["url"] == "http://127.0.0.1:9/mcp"


def test_iter_provider_specs_dedupes_top_level_and_spec_by_name():
    from mas.runtime.registry.tool_provider_registry import iter_provider_specs

    entries = iter_provider_specs(
        {
            "providers": [{"name": "mcp", "kind": "mcp", "url": "http://old.invalid/mcp"}],
            "spec": {
                "providers": [
                    {"name": "mcp", "kind": "mcp", "url": "http://127.0.0.1:9001/mcp"},
                    {"name": "in-process", "kind": "local", "tools": "*"},
                ]
            },
        }
    )
    by_name = {e["name"]: e for e in entries}
    assert set(by_name) == {"mcp", "in-process"}
    assert by_name["mcp"]["url"] == "http://127.0.0.1:9001/mcp"


def test_registry_invalidate_forwards_to_provider():
    class _Prov:
        provider_name = "p"
        tools_claim = ("t",)
        origin = "external"
        dropped = False

        def has_tools(self):
            return True

        def list_tools(self, *, ctx=None):
            return [{"name": "t"}]

        def call_tool(self, tool_name, arguments, *, ctx=None, user=""):
            return {}

        def invalidate(self):
            self.dropped = True

    registry = ToolProviderRegistry()
    provider = _Prov()
    registry.register_provider(provider)
    registry.initialize()
    registry.invalidate()
    assert provider.dropped is True
    assert registry._routes is None
