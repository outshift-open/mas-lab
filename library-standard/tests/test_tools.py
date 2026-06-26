#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-library-standard v2 tests."""

from mas.library.standard.tools import execute_tool


def test_calculator_tool():
    assert "391" in execute_tool("calculator", user="17 × 23", arguments={"expression": "17*23"})


def test_web_search_mock_fallback():
    out = execute_tool("web-search", arguments={"query": "test query"})
    assert out and "web-search" in out.lower() or "query" in out.lower()


def test_unknown_tool_returns_none():
    assert execute_tool("nonexistent_tool_xyz") is None
