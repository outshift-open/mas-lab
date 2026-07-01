#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ApplicationRunner registry — discovers built-in and entry-point backends."""
from __future__ import annotations

import logging
from typing import Dict, Type

from mas.lab.runners.constants import normalize_runner_id

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "mas.lab.runners"


class ApplicationRunnerRegistry:
    """Registry of :class:`ApplicationRunnerProtocol` implementations."""

    _runners: Dict[str, Type[ApplicationRunnerProtocol]] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        if cls._initialized:
            return
        cls._initialized = True

        try:
            from importlib.metadata import entry_points

            for ep in entry_points(group=_ENTRY_POINT_GROUP):
                if ep.name in cls._runners:
                    continue
                try:
                    cls._runners[ep.name] = ep.load()
                except Exception as load_exc:
                    logger.warning("Failed to load runner %r: %s", ep.name, load_exc)
        except Exception as exc:
            logger.debug("Runner entry-point discovery failed: %s", exc)

    @classmethod
    def register(cls, runner_id: str, runner_cls: Type[ApplicationRunnerProtocol]) -> None:
        cls._runners[runner_id] = runner_cls

    @classmethod
    def get(cls, runner_id: str) -> ApplicationRunnerProtocol:
        cls._ensure_initialized()
        rid = normalize_runner_id(runner_id)
        runner_cls = cls._runners.get(rid)
        if runner_cls is None:
            available = cls.available()
            raise ValueError(
                f"ApplicationRunner {runner_id!r} is not registered. "
                f"Available: {available}."
            )
        return runner_cls()

    @classmethod
    def available(cls) -> list[str]:
        cls._ensure_initialized()
        return sorted(cls._runners)

    @classmethod
    def reset(cls) -> None:
        cls._runners.clear()
        cls._initialized = False
