#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Viz-registry adapters for mas.lab.plots plotters.

These adapters bridge :mod:`mas.lab.plots` and the tutorial UI viz-registry
(``mas.lab.tutorial.renderers.viz_registry``).  They are *decoupled* from the
registry itself: each function accepts a ``register_fn`` argument so they can
be called from any context without depending on the tutorial package.

Usage — single line in ``renderers/__init__.py`` when ready::

    from mas.lab.plots._viz_adapters import register_pipeline_viz, register_multilevel_viz
    register_pipeline_viz(register)
    register_multilevel_viz(register)

The ``register`` callable must have the signature expected by
``viz_registry.register(types, name, label, render_fn)`` where
``render_fn(content, data=None, params={}) -> str``.

Registration order determines the default tab in the UI.  Call
``register_pipeline_viz`` **before** the existing Mermaid ``"pipeline"``
registration to make ``"pipeline-dag"`` the default tab.  For ``events``,
``register_multilevel_viz`` adds ``"multilevel"`` as the primary viz for
``events.jsonl`` content types.
"""

import json
import logging
from typing import Any, Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline viz adapter
# ---------------------------------------------------------------------------


def register_pipeline_viz(register_fn: Callable[..., Any]) -> None:
    """Register :func:`~mas.lab.plots.pipeline_diagram.plot_pipeline` with the
    viz registry as a ``"pipeline-dag"`` viz for content type ``"pipeline"``.

    The rendered output is a ``<div class="viz-pipeline-dag">`` wrapping the
    ``plot_pipeline()`` SVG (no external dependencies, renders inline).

    Call this *before* the existing Mermaid ``"pipeline"`` registration so
    that the DAG view becomes the default tab in the UI.

    Parameters
    ----------
    register_fn:
        The ``register(types, name, label, render_fn)`` callable from
        ``mas.lab.tutorial.renderers.viz_registry``.
    """
    try:
        from mas.lab.plots.pipeline_diagram import plot_pipeline
    except ImportError as exc:
        log.warning("register_pipeline_viz: cannot import plot_pipeline — %s", exc)
        return

    def _render_pipeline(
        content: Any,
        data: Any = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        try:
            svg = plot_pipeline(content, fmt="svg")
            return f'<div class="viz-pipeline-dag">{svg}</div>'
        except Exception as exc:
            log.debug("render_pipeline_viz error: %s", exc, exc_info=True)
            return f"<pre class=\"viz-error\">Pipeline DAG error: {exc}</pre>"

    register_fn("pipeline", "pipeline-dag", "DAG", _render_pipeline)


# ---------------------------------------------------------------------------
# Multilevel trajectory viz adapter
# ---------------------------------------------------------------------------


def register_multilevel_viz(register_fn: Callable[..., Any]) -> None:
    """Register :func:`~mas.lab.plots.multilevel_trajectory.plot_multilevel_trajectory`
    with the viz registry as a ``"multilevel"`` viz for content type ``"events"``.

    The ``content`` argument is expected to be the raw ``events.jsonl`` text
    (one JSON object per line).  The renderer parses the text and calls
    ``plot_multilevel_trajectory(events, fmt="html")`` which produces a
    self-contained HTML fragment with D3 tooltips and interactive navigation.

    Parameters
    ----------
    register_fn:
        The ``register(types, name, label, render_fn)`` callable from
        ``mas.lab.tutorial.renderers.viz_registry``.
    """
    try:
        from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory
    except ImportError as exc:
        log.warning("register_multilevel_viz: cannot import plot_multilevel_trajectory — %s", exc)
        return

    def _render_multilevel(
        content: Any,
        data: Any = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        try:
            if isinstance(content, list):
                events = content
            else:
                # Parse JSONL text
                events = [
                    json.loads(line)
                    for line in str(content).splitlines()
                    if line.strip()
                ]
            return plot_multilevel_trajectory(events, fmt="html")
        except Exception as exc:
            log.debug("render_multilevel_viz error: %s", exc, exc_info=True)
            return f"<pre class=\"viz-error\">Multilevel trajectory error: {exc}</pre>"

    register_fn("events", "multilevel", "Multilevel", _render_multilevel)
