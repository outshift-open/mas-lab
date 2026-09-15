from __future__ import annotations

from typing import Any, Dict

from mas.runtime.plugins.mcp_provider_plugin import MCPClientFactory, MCPProviderPlugin
from mas.runtime.registry.tool_provider_registry import ToolProviderRegistry


class _FakeClientSession:
    async def list_tools(self):
        return [{"name": "calculator", "description": "calc", "inputSchema": {"type": "object"}}]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        assert tool_name == "calculator"
        assert arguments == {"expression": "2 + 2"}
        return {"content": [{"type": "text", "text": "4"}]}


class _FakeMCPProviderFactory:
    def __init__(self, **_kwargs):
        pass

    def create_client(self):
        return _FakeClientSession()


def test_mcp_provider_plugin_registers_tool_provider():
    registry = ToolProviderRegistry()
    plugin = MCPProviderPlugin(factory_cls=_FakeMCPProviderFactory)

    plugin.on_manifest_load(
        {
            "providers": [
                {
                    "kind": "mcp",
                    "name": "calc-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "dummy_server"],
                }
            ]
        },
        registry,
    )

    assert registry.has_tools()
    tools = registry.list_tools()
    assert any(tool["name"] == "calculator" for tool in tools)
    assert registry.call_tool("calculator", {"expression": "2 + 2"}) == {"result": "4"}


def test_mcp_factory_supports_streamable_http_url():
    factory = MCPClientFactory(transport="streamable-http", url="http://127.0.0.1:9001/mcp")
    client = factory.create_client()
    assert client is not None
    assert client._client.url == "http://127.0.0.1:9001/mcp"
