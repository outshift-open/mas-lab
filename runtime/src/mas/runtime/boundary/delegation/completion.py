#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest-declared delegation result completion checks."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_VERIFICATION_LINE = re.compile(
    r"VERIFICATION:\s*(APPROVED|FLAGGED|REJECTED)\b",
    re.IGNORECASE | re.MULTILINE,
)

CompletionCheck = Callable[[str], bool]

_MAX_COMPLETION_ATTEMPTS = 2

_CHECKERS: dict[str, CompletionCheck] = {
    "verification_line": lambda text: bool(_VERIFICATION_LINE.search(text)),
}


def completion_check_for_type(check_type: str | None) -> CompletionCheck | None:
    if not check_type:
        return None
    return _CHECKERS.get(check_type)


def max_completion_attempts() -> int:
    return _MAX_COMPLETION_ATTEMPTS


def verification_status(text: str) -> str | None:
    match = _VERIFICATION_LINE.search(text)
    if not match:
        return None
    return match.group(1).upper()


def incomplete_verification_fallback(partial: str) -> str:
    body = partial.rstrip()
    if body:
        body += "\n\n"
    return (
        f"{body}VERIFICATION: FLAGGED — Verifier response was incomplete; "
        "manual review required before run_action."
    )


def continuation_prompt_for_verification(partial: str) -> str:
    return (
        "Your prior verification response was incomplete and did not end with "
        "VERIFICATION: APPROVED, VERIFICATION: FLAGGED — <reason>, or "
        "VERIFICATION: REJECTED — <reason>.\n\n"
        f"Partial output:\n{partial.rstrip()}\n\n"
        "Complete the verification now. End with exactly one VERIFICATION line."
    )


def peer_completion_checks_from_manifests(
    peer_manifests: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Map peer agent id → completion_check type from loaded manifests."""
    from mas.runtime.boundary.context.manifest_context import completion_check_type_from_agent

    out: dict[str, str] = {}
    for peer_id, manifest in peer_manifests.items():
        check_type = completion_check_type_from_agent(manifest)
        if check_type:
            out[peer_id] = check_type
    return out
