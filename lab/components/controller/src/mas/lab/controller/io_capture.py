#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Capture stdout/stderr from worker threads into WorkerRecord buffers."""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mas.lab.controller.worker_model import WorkerRecord


class _StreamCapture:
    def __init__(self, record: "WorkerRecord", attr: str) -> None:
        self._record = record
        self._attr = attr

    def write(self, text: str) -> int:
        if text:
            getattr(self._record, f"append_{self._attr}_chunk")(text)
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


@contextmanager
def capture_worker_io(record: "WorkerRecord"):
    """Redirect sys.stdout/stderr and logging into the worker record.

    Logging handlers are bound when the daemon starts (often to daemon.log),
    so replacing sys.stderr alone does not move ``logger.error`` into the
    stream the CLI polls.  A temporary StreamHandler writes those lines
    into the worker record as well.
    """
    out = _StreamCapture(record, "stdout")
    err = _StreamCapture(record, "stderr")
    old_out, old_err = sys.stdout, sys.stderr
    handler = logging.StreamHandler(err)
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    sys.stdout, sys.stderr = out, err  # type: ignore[assignment]
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
        handler.close()
        sys.stdout, sys.stderr = old_out, old_err
