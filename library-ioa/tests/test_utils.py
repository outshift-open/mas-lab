#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from library_ioa.utils import translate_mcp_error


def test_translate_mcp_error_shape() -> None:
    err = ConnectionError("mcp down")
    mapped = translate_mcp_error(err)
    assert mapped == {
        "status": "error",
        "error": "mcp down",
        "type": "ConnectionError",
        "is_error": True,
    }
