#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Threshold circuit breaker — library plugin wrapping engine I/O."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from mas.runtime.reliability.classes import CircuitOpenError, FailureClass
from mas.runtime.reliability.log import LOGGER, extra

PLUGIN_ID = "circuit_breaker"
_FAILURE_CLASSES = {item.value: item for item in FailureClass}


def _parse_on(raw: Any) -> tuple[FailureClass, ...]:
    if raw is None:
        return (FailureClass.UNAVAILABLE,)
    if raw is True:
        return (FailureClass.UNAVAILABLE,)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise ValueError("circuit_breaker.on must be a list of failure-class names")
    out: list[FailureClass] = []
    for item in raw:
        key = str(item).strip().lower()
        if key not in _FAILURE_CLASSES:
            raise ValueError(
                f"circuit_breaker.on: unknown failure class {item!r} "
                f"(expected {sorted(_FAILURE_CLASSES)})"
            )
        out.append(_FAILURE_CLASSES[key])
    return tuple(out) or (FailureClass.UNAVAILABLE,)


@dataclass
class _BreakerState:
    consecutive_failures: int = 0
    opened_at: float = 0.0
    half_open: bool = False


class ThresholdCircuitBreaker:
    """Fail-fast after ``failure_threshold`` consecutive matching failures.

    Consulted inside engine execute (infra retry), not by the kernel.
    """

    plugin_id = "circuit_breaker@v1"
    name = "threshold"

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
        on: Any = None,
        enabled: bool = True,
        **_raw: object,
    ) -> None:
        if not isinstance(failure_threshold, int) or isinstance(failure_threshold, bool) or failure_threshold < 1:
            raise ValueError("circuit_breaker.failure_threshold must be an integer >= 1")
        if (
            not isinstance(reset_timeout_s, (int, float))
            or isinstance(reset_timeout_s, bool)
            or reset_timeout_s < 0
        ):
            raise ValueError("circuit_breaker.reset_timeout_s must be a number >= 0")
        self.enabled = bool(enabled)
        self.failure_threshold = failure_threshold
        self.reset_timeout_s = float(reset_timeout_s)
        self.on = _parse_on(on)
        self._states: dict[str, _BreakerState] = {}

    def before_call(self, target: str) -> None:
        if not self.enabled:
            return
        state = self._states.get(target)
        if state is None or state.opened_at <= 0:
            return
        elapsed = time.monotonic() - state.opened_at
        if elapsed >= self.reset_timeout_s:
            state.half_open = True
            LOGGER.info(
                "circuit half-open for %s; allowing one probe",
                target,
                extra=extra(target=target, outcome="circuit_half_open"),
            )
            return
        remaining = self.reset_timeout_s - elapsed
        LOGGER.warning(
            "circuit open for %s; retry after %.1fs",
            target,
            remaining,
            extra=extra(
                target=target,
                outcome="circuit_open",
                delay_s=round(remaining, 3),
            ),
        )
        raise CircuitOpenError(target, reset_timeout_s=remaining)

    def record_success(self, target: str) -> None:
        state = self._states.pop(target, None)
        if state is not None and (state.opened_at > 0 or state.half_open):
            LOGGER.info(
                "circuit closed for %s after success",
                target,
                extra=extra(target=target, outcome="circuit_closed"),
            )

    def record_failure(self, target: str, failure_class: FailureClass) -> None:
        if not self.enabled or failure_class not in self.on:
            return
        state = self._states.setdefault(target, _BreakerState())
        if state.half_open:
            state.half_open = False
            state.consecutive_failures = self.failure_threshold
            state.opened_at = time.monotonic()
            LOGGER.warning(
                "circuit re-opened for %s after failed probe (%s)",
                target,
                failure_class.value,
                extra=extra(
                    target=target,
                    failure_class=failure_class.value,
                    outcome="circuit_open",
                    attempt=state.consecutive_failures,
                ),
            )
            return
        state.consecutive_failures += 1
        if state.consecutive_failures >= self.failure_threshold:
            state.opened_at = time.monotonic()
            LOGGER.warning(
                "circuit open for %s after %s consecutive %s failures",
                target,
                state.consecutive_failures,
                failure_class.value,
                extra=extra(
                    target=target,
                    failure_class=failure_class.value,
                    outcome="circuit_open",
                    attempt=state.consecutive_failures,
                    max_attempts=self.failure_threshold,
                ),
            )

    def is_open(self, target: str) -> bool:
        state = self._states.get(target)
        if state is None or state.opened_at <= 0:
            return False
        return (time.monotonic() - state.opened_at) < self.reset_timeout_s
