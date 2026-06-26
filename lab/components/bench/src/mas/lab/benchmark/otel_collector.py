#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""OtelCollectorLifecycle — start/stop a Docker OTel collector for benchmark runs.

When a benchmark flavour requests ``otel_extended`` instrumentation,
``run_mas_benchmark`` wraps its execution loop with this context manager.  It:

1. Runs ``docker compose -p mas-benchmark-otel up -d --wait`` so spans have
   somewhere to land before the first run fires.
2. Sets ``OTEL_ENDPOINT=http://localhost:{port}`` in the process environment
   so the ``otel_extended`` plugin can export spans.
3. Runs ``docker compose down`` on exit (unless *skip_teardown* is set).

If Docker is not available, or the compose file is not found, the instance
initialises as a **graceful no-op**: it logs a warning, sets no env var, and
the benchmark continues without OTel.

Usage (automatic — driven by flavour spec)::

    from mas.lab.benchmark.otel_collector import resolve_collector

    _otel = resolve_collector(_flavour, experiment_dir, output_dir)
    with (_otel or contextlib.nullcontext()):
        # benchmark loop
        ...
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 4318
_COMPOSE_PROJECT = "mas-benchmark-otel"


class OtelCollectorLifecycle:
    """Context manager that starts/stops a dockerised OTel collector.

    Args:
        compose_file:   Path to the docker-compose file for the collector.
        traces_dir:     Host directory mounted at ``/var/lib/otel`` inside the
                        container (OTel traces are written here).
        port:           OTLP HTTP port exposed on the host (default 4318).
        skip_teardown:  When True ``docker compose down`` is skipped on exit,
                        so you can inspect spans after the run.
    """

    def __init__(
        self,
        compose_file: Path,
        traces_dir: Path,
        port: int = _DEFAULT_PORT,
        skip_teardown: bool = False,
    ) -> None:
        self.compose_file = compose_file
        self.traces_dir = traces_dir
        self.port = port
        self.skip_teardown = skip_teardown
        self._active = False
        self._prev_endpoint: Optional[str] = None

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "OtelCollectorLifecycle":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the collector container and export OTEL_ENDPOINT."""
        if not self._preflight():
            return

        self.traces_dir.mkdir(parents=True, exist_ok=True)

        env = {**os.environ}
        logger.info("Starting OTel collector (docker compose up -d --wait) …")

        result = subprocess.run(
            [
                "docker", "compose",
                "-p", _COMPOSE_PROJECT,
                "-f", str(self.compose_file),
                "up", "-d", "--wait",
            ],
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.warning(
                "docker compose up failed (exit %d) — OTel collector disabled.\n%s",
                result.returncode,
                result.stderr[:600],
            )
            return

        self._active = True
        self._prev_endpoint = os.environ.get("OTEL_ENDPOINT")
        os.environ["OTEL_ENDPOINT"] = f"http://localhost:{self.port}"
        logger.info(
            "OTel collector ready → OTEL_ENDPOINT=http://localhost:%d  traces → %s",
            self.port,
            self.traces_dir / "traces.jsonl",
        )

    def stop(self) -> None:
        """Stop the collector container and restore OTEL_ENDPOINT."""
        # Always restore the env var, even if we never started
        if self._prev_endpoint is not None:
            os.environ["OTEL_ENDPOINT"] = self._prev_endpoint
        else:
            os.environ.pop("OTEL_ENDPOINT", None)

        if not self._active:
            return

        if self.skip_teardown:
            logger.info(
                "OTel collector left running (skip_teardown=True). "
                "Stop manually:  docker compose -p %s -f %s down",
                _COMPOSE_PROJECT,
                self.compose_file,
            )
            return

        logger.info("Stopping OTel collector …")
        subprocess.run(
            [
                "docker", "compose",
                "-p", _COMPOSE_PROJECT,
                "-f", str(self.compose_file),
                "down",
            ],
            capture_output=True,
        )
        self._active = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preflight(self) -> bool:
        """Return True when the compose file exists and Docker is available."""
        if not self.compose_file.exists():
            logger.warning(
                "OTel compose file not found: %s — collector will not start.",
                self.compose_file,
            )
            return False

        check = subprocess.run(
            ["docker", "info"],
            capture_output=True,
        )
        if check.returncode != 0:
            logger.warning(
                "Docker is not available (docker info returned %d) — "
                "OTel collector disabled. Benchmark will run without spans.",
                check.returncode,
            )
            return False

        return True


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def resolve_collector(
    flavour,
    experiment_dir: Path,
    output_dir: Path,
    skip_teardown: bool = False,
) -> Optional[OtelCollectorLifecycle]:
    """Return an ``OtelCollectorLifecycle`` when the flavour uses otel_extended.

    Returns ``None`` if the flavour doesn't request ``otel_extended``, so the
    caller can use ``with (resolve_collector(...) or contextlib.nullcontext()):``
    without any conditional logic.

    Compose file resolution::

        <experiment_dir>/infra/docker-compose.otel.yml
    """
    if flavour is None:
        return None

    try:
        backend = flavour.spec.observability.backend
    except AttributeError:
        return None

    if backend != "otel_extended":
        return None

    compose_file = experiment_dir / "infra" / "docker-compose.otel.yml"
    traces_dir = output_dir / "otel"

    return OtelCollectorLifecycle(
        compose_file=compose_file,
        traces_dir=traces_dir,
        skip_teardown=skip_teardown,
    )
