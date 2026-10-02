#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared structured logging for retries, the breaker, and ingress policy."""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger("mas.runtime.reliability")


def extra(**fields: Any) -> dict[str, Any]:
    """LogRecord extras keyed ``mas.*`` so operators can filter JSON logs."""
    out: dict[str, Any] = {"mas.reliability": True}
    for key, value in fields.items():
        if value is None or value == "":
            continue
        out[f"mas.{key}"] = value
    return out


def log_retry(
    *,
    target: str,
    failure_class: str,
    failure_code: str,
    attempt: int,
    max_attempts: int,
    delay_s: float,
    message: str,
) -> None:
    LOGGER.warning(
        "%s %s/%s failed (%s %s); retrying in %.3fs",
        target or "call",
        attempt,
        max_attempts,
        failure_class,
        failure_code or message,
        delay_s,
        extra=extra(
            target=target,
            failure_class=failure_class,
            failure_code=failure_code,
            attempt=attempt,
            max_attempts=max_attempts,
            delay_s=round(delay_s, 3),
            outcome="retry",
        ),
    )


def log_no_retry(
    *,
    target: str,
    failure_class: str,
    failure_code: str,
    attempt: int,
    max_attempts: int,
    message: str,
) -> None:
    LOGGER.warning(
        "%s failed (%s %s); not retrying: %s",
        target or "call",
        failure_class,
        failure_code,
        message,
        extra=extra(
            target=target,
            failure_class=failure_class,
            failure_code=failure_code,
            attempt=attempt,
            max_attempts=max_attempts,
            outcome="no_retry",
        ),
    )


def log_exhausted(
    *,
    target: str,
    failure_class: str,
    failure_code: str,
    attempt: int,
    max_attempts: int,
    message: str,
) -> None:
    LOGGER.error(
        "%s failed after %s/%s attempts (%s %s): %s",
        target or "call",
        attempt,
        max_attempts,
        failure_class,
        failure_code,
        message,
        extra=extra(
            target=target,
            failure_class=failure_class,
            failure_code=failure_code,
            attempt=attempt,
            max_attempts=max_attempts,
            outcome="exhausted",
        ),
    )


def log_ingress(
    *,
    action: str,
    failure_class: str,
    failure_code: str,
    retry_count: int,
    max_retries: int,
    message: str,
) -> None:
    if action in ("ALLOW",) and not failure_class:
        return
    level = LOGGER.error if action in ("BLOCK", "EXIT") else LOGGER.warning
    if action == "ALLOW" and failure_class:
        level = LOGGER.info
    level(
        "ingress %s (%s %s, gov retry %s/%s): %s",
        action,
        failure_class or "untyped",
        failure_code,
        retry_count,
        max_retries,
        message,
        extra=extra(
            failure_class=failure_class,
            failure_code=failure_code,
            attempt=retry_count,
            max_attempts=max_retries,
            outcome=f"ingress_{action.lower()}",
        ),
    )


def log_recovered(*, target: str, attempts: int) -> None:
    if attempts <= 1:
        return
    LOGGER.info(
        "%s succeeded after %s attempts",
        target or "call",
        attempts,
        extra=extra(target=target, attempt=attempts, outcome="recovered"),
    )
