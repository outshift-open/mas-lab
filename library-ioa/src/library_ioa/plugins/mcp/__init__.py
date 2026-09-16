#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCP support package."""

from library_ioa.plugins.mcp.contract import (
    as_mas_tool_result,
    as_mas_tool_spec,
    mas_tool_document_to_mcp,
)
from library_ioa.plugins.mcp.provider import MCPClientFactory, MCPToolProvider
from library_ioa.plugins.mcp.spec import MCPProviderSpec

__all__ = [
    "MCPClientFactory",
    "MCPProviderSpec",
    "MCPToolProvider",
    "as_mas_tool_result",
    "as_mas_tool_spec",
    "mas_tool_document_to_mcp",
]
