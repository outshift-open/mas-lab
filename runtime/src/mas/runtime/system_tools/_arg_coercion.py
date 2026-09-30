#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared pydantic field coercion for system-tool arguments.

Some tool-calling backends JSON-encode a nested object argument as a string
instead of emitting a native object (e.g. ``metadata='{"a": 1}'`` instead of
``metadata={"a": 1}``). Pydantic does not auto-parse a JSON string into a
``dict``-typed field, so this raises a validation error for a value the
model did provide, just in the wrong shape -- observed crashing whole agent
runs on ``inform_user``'s and ``request_human_input``'s ``dict[str, Any]``
fields. Attach as a ``mode="before"`` field_validator on any such field.
"""

from __future__ import annotations

import json
from typing import Any


def coerce_json_string_to_dict(value: Any) -> Any:
    """Parse a JSON-object string into a dict; pass anything else through unchanged.

    Only handles the case the value is a string that decodes to a JSON
    object -- any other shape (already a dict, not valid JSON, a JSON array
    or scalar) is returned as-is and left for the field's own type
    validation to accept or reject normally.
    """
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    return parsed if isinstance(parsed, dict) else value
