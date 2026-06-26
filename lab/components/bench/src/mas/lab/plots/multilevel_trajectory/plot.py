#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Public plot entry points."""

from pathlib import Path
from typing import Any, Union

from mas.lab.plots.multilevel_trajectory.chart_data import _build_chart_data, _fmt_d3_html
from mas.lab.plots.multilevel_trajectory.dag import _build_dag
from mas.lab.plots.multilevel_trajectory.records import _build_call_records
from mas.lab.plots.multilevel_trajectory.svg import _render_svg
from mas.lab.plots.trajectory import load_trace

def plot_multilevel_trajectory(
    trace: Union[str, Path, list[dict]],
    fmt: str = "html",
    title: str = "MAS Multilevel Trajectory",
    width_mode: str = "log",
    show_user_actors: bool = True,
    show_time_axis: bool = True,
    show_provenance: bool = True,
    annotations: dict | None = None,
) -> str:
    """Generate a multilevel trajectory DAG diagram.

    Parameters
    ----------
    trace:
        Event list, JSONL file path, or run_id string.
    fmt:
        ``"html"`` (default) — self-contained dark HTML with JS tooltips.
        ``"svg"``  — raw SVG string.
    title:
        Diagram title.
    width_mode:
        Column-width scaling for transitions.

        ``"fixed"``         Equal width for every column (default).
        ``"proportional"``  Width proportional to wall-clock duration.
                            Long LLM calls get wide columns; tool calls may
                            be very narrow.
        ``"log"``           Logarithmic scaling — compresses very long calls
                            while keeping short calls readable.
    show_user_actors:
        When ``True`` (default) the first and last states are rendered as amber
        stickman actor shapes in the Session lane, with a ``W`` (write/input)
        badge on the entry node and an ``R`` (read/output) badge on the exit
        node.  Set to ``False`` to render those states as ordinary boxes.
    show_time_axis:
        When ``True`` (default, HTML only) a time ruler is drawn below the
        diagram showing relative timestamps (+Xs) at each state boundary.
        Hover tooltips also always include the call start/end times and type.
    show_provenance:
        When ``True`` (default) each LLM call and processing call that carries
        L4 context-provenance data (``context_part_contributed`` events, or
        per-actor ``segments``) renders a rich CPR card on click/hover — a
        pie chart of source categories, token counts, and a per-part chain.
        Set to ``False`` to omit all CPR data from the output (lighter HTML,
        useful for sharing / publishing).
    """
    if not isinstance(trace, list):
        trace = load_trace(trace)
    if not trace:
        return "(empty trace)"

    records = _build_call_records(trace)
    if not records:
        return "(no timed execution records found in trace)"

    state_reg, lanes = _build_dag(records, trace, show_provenance=show_provenance)
    if not lanes:
        return "(empty DAG)"

    fmt = fmt.lower()
    if fmt == "svg":
        return _render_svg(state_reg, lanes, title=title, width_mode=width_mode,
                           show_user_actors=show_user_actors)
    if fmt == "html":
        data = _build_chart_data(state_reg, lanes, title=title, width_mode=width_mode,
                                 show_user_actors=show_user_actors,
                                 show_time_axis=show_time_axis,
                                 annotations=annotations,
                                 records=records)
        return _fmt_d3_html(data)
    raise ValueError(f"Unknown format '{fmt}'. Use: html, svg")


def plot_multilevel_trajectory_from_kg(
    source: "Union[dict, Path, str, Any]",
    query: "Any | None" = None,
    fmt: str = "html",
    title: str = "MAS Multilevel Trajectory",
    width_mode: str = "log",
    show_user_actors: bool = True,
    show_time_axis: bool = True,
    show_provenance: bool = True,
    annotations: dict | None = None,
) -> str:
    """Generate a multilevel trajectory diagram from a KG (kg.json).

    This is the KG-backed counterpart of :func:`plot_multilevel_trajectory`.
    Instead of consuming raw ``events.jsonl`` (start/end pairs), it reads the
    already-collapsed call records from a Knowledge Graph and applies an
    optional :class:`~mas.lab.plots.kg_adapter.FacetQuery` filter before
    rendering.

    Parameters
    ----------
    source:
        One of:

        * A ``KGSource`` instance (most flexible — supports live Neo4j sources).
        * A ``dict`` — raw ``{"nodes": [...], "edges": [...]}`` KG payload.
        * A ``str`` or ``Path`` — path to a ``kg.json`` file.
    query:
        Optional :class:`~mas.lab.plots.kg_adapter.FacetQuery` instance (or
        ``None`` for the full KG).  Filters by ``session_id``, ``run_id``,
        ``agent_ids``, ``call_types``, and/or ``time_range``.
    fmt:
        ``"html"`` (default) or ``"svg"`` — same as
        :func:`plot_multilevel_trajectory`.
    title, width_mode, show_user_actors, show_time_axis, show_provenance, annotations:
        Same semantics as :func:`plot_multilevel_trajectory`.

        .. note::
            KG-backed traces do not carry ``context_part_contributed`` events,
            so ``show_provenance=True`` will simply produce no CPR cards when
            the source KG was generated without an L4 observability plugin.
            The parameter is honoured for forward-compatibility (when future
            KG exporters include per-segment provenance fields).

    Returns
    -------
    str
        SVG string or self-contained HTML page.

    Examples
    --------
    ::

        from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory_from_kg
        from mas.lab.plots.kg_adapter import FacetQuery, KGSource

        # From a kg.json file
        html = plot_multilevel_trajectory_from_kg("path/to/kg.json")

        # Filter to two agents
        html = plot_multilevel_trajectory_from_kg(
            "path/to/kg.json",
            query=FacetQuery(agent_ids=["orchestrator", "analyst"]),
        )

        # From a live Neo4j source (KGQuerySource extends KGSource)
        source = KGQuerySource(session_id="abc-123")
        html = plot_multilevel_trajectory_from_kg(source)

    Pipeline step usage (``PlotMultilevelTrajectoryKGStep``)::

        - name: plot-trajectory
          type: plot_multilevel_trajectory_kg
          depends_on: [normalize-native]
          config:
            agent_ids: [orchestrator, analyst]
            fmt: html
    """
    from mas.lab.plots.kg_adapter import KGSource, FacetQuery as _FQ

    # Normalise source
    if isinstance(source, (str, Path, dict)):
        if isinstance(source, dict):
            src = KGSource(source)
        else:
            src = KGSource.from_file(source)
    else:
        # Assume KGSource or compatible (duck typing: must have .load())
        src = source

    # Normalise query
    q: "_FQ | None" = None
    if query is not None:
        if isinstance(query, dict):
            q = _FQ.from_dict(query)
        else:
            q = query

    records, events = src.load(q)
    if not records:
        return "(no call records after applying query)"

    state_reg, lanes = _build_dag(records, events, show_provenance=show_provenance)
    if not lanes:
        return "(empty DAG)"

    fmt = fmt.lower()
    if fmt == "svg":
        return _render_svg(state_reg, lanes, title=title, width_mode=width_mode,
                           show_user_actors=show_user_actors)
    if fmt == "html":
        data = _build_chart_data(state_reg, lanes, title=title, width_mode=width_mode,
                                 show_user_actors=show_user_actors,
                                 show_time_axis=show_time_axis,
                                 annotations=annotations,
                                 records=records)
        return _fmt_d3_html(data)
    raise ValueError(f"Unknown format '{fmt}'. Use: html, svg")
