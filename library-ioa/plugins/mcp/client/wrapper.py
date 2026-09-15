from typing import Any, Dict, List, Optional
import logging
from mcp.client import MCPClient

logger = logging.getLogger(__name__)

class MCPClientWrapper:
    """
    A high-level wrapper for MCP clients to be used within the synchronous 
    mas-lab runtime. This wrapper handles the conversion between 
    async MCP operations and the sync execution expected by ToolContract.
    """

    def __init__(self, client: MCPClient):
        self._client = client

    async def list_tools(self) -> List[Dict[str, Any]]:
        return await self._client.list_tools()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.call_tool(tool_name, arguments)

    async def connect(self):
        await self._client.connect()

    async def disconnect(self):
        await self._client.disconnect()
