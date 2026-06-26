#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""D3 chart data serialization and HTML template formatting."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Union

from mas.lab.plots.multilevel_trajectory.dag import _build_dag
from mas.lab.plots.multilevel_trajectory.models import LaneDef, StateNode, TransNode
from mas.lab.plots.multilevel_trajectory.records import _build_call_records
from mas.lab.plots.multilevel_trajectory.svg import _esc
from mas.lab.plots.trajectory import load_trace

def _build_chart_data(
    state_reg: dict[float, StateNode],
    lanes: list[LaneDef],
    title: str,
    width_mode: str,
    show_user_actors: bool = True,
    show_time_axis: bool = True,
    annotations: dict | None = None,
    records: list[dict] | None = None,
) -> dict:
    """Serialize the DAG to a JSON-serialisable dict for the D3 renderer.

    Boundaries are already structurally aligned by ``_align_record_boundaries``
    before the DAG is assembled, so every lane uses the exact same timestamp
    set — no heuristic timestamp merging needed here.
    """
    all_buckets = sorted(state_reg.keys())
    _numbered_buckets2 = [b for b in all_buckets if not state_reg[b].label_override]
    _numbered_seq2     = {b: i + 1 for i, b in enumerate(_numbered_buckets2)}
    state_num   = {
        b: _numbered_seq2.get(b, _numbered_seq2.get(
            max((nb for nb in _numbered_buckets2 if nb < b), default=_numbered_buckets2[0])
            if _numbered_buckets2 else b, 1
        ))
        for b in all_buckets
    }

    bucket_to_lanes: dict[float, list[int]] = defaultdict(list)
    for li, lane in enumerate(lanes):
        seen: set[float] = set()
        for el in lane.sequence:
            if isinstance(el, StateNode) and el.ts not in seen:
                bucket_to_lanes[el.ts].append(li)
                seen.add(el.ts)

    shared_buckets = [
        {"ts": b, "laneIndices": sorted(set(ls))}
        for b, ls in sorted(bucket_to_lanes.items())
        if len(set(ls)) >= 2
    ]

    ann = annotations or {}
    hl_agents = {str(a).lower() for a in (ann.get("highlight_agents") or [])}

    # gap_ts_set: timestamps where at least one pin was resolved.
    # ALL lanes sharing that timestamp get gapMarker=true (visible ring).
    # pin_map: (lane_id, ts) → {note, excerpt}  — only the matching agent lane
    # carries the annotation text; other lanes get the ring only.
    gap_ts_set: set[float] = set()
    pin_map: dict[tuple[str, float], dict] = {}
    pins = ann.get("pins") or []
    if pins and records:
        cid_to_rec = {r["call_id"]: r for r in records if r.get("call_id")}
        for pin in pins:
            cid = str(pin.get("call_id", "")).strip()
            if not cid:
                continue
            matched = cid_to_rec.get(cid)
            if matched is None:
                # prefix match
                for rec_id, rec in cid_to_rec.items():
                    if rec_id.startswith(cid) or cid.startswith(rec_id):
                        matched = rec
                        break
            if matched:
                end_ts = matched.get("end_ts") or matched.get("start_ts")
                if end_ts:
                    gap_ts_set.add(end_ts)   # ring on every lane at this ts
                    for lane in lanes:
                        if (lane.lane_id == "agents"
                                or lane.lane_id.lower() == matched.get("agent_id", "").lower()):
                            pin_map[(lane.lane_id, end_ts)] = {
                                "note":    str(pin.get("note", "") or ""),
                                "excerpt": str(pin.get("excerpt", "") or ""),
                            }
                            break

    lanes_json = []
    for lane in lanes:
        seq: list[dict] = []
        for el in lane.sequence:
            if isinstance(el, StateNode):
                _pin = pin_map.get((lane.lane_id, el.ts), {})
                seq.append({
                    "type":          "state",
                    "ts":            el.ts,
                    "num":           state_num.get(el.ts, 0),
                    "nodeId":        el.node_id,
                    "labelOverride": el.label_override,
                    "hover":         el.hover,
                    "hoverByLane":   el.hover_by_lane,
                    "userEntry":     el.is_user_entry,
                    "userExit":      el.is_user_exit,
                    "laneRestart":   el.is_lane_restart,
                    "connectorOnly": el.ts in lane.connector_only_ts,
                    "interrupted":   el.is_interrupted,
                    "isError":       el.is_error,
                    "gapMarker":     el.ts in gap_ts_set,
                    "pinNote":       _pin.get("note")    or None,
                    "pinExcerpt":    _pin.get("excerpt") or None,
                    **({"isFork": True, "parallelGroupId": el.parallel_group_id,
                        "parallelSize": el.parallel_size} if el.is_fork else {}),
                    **({"isJoin": True, "parallelGroupId": el.parallel_group_id,
                        "parallelSize": el.parallel_size} if el.is_join else {}),
                    **({
                        "cprData": el.cpr_data,
                        "model":   el.model,
                    } if el.cpr_data else {}),
                })
            elif isinstance(el, TransNode):
                _td: dict[str, Any] = {
                    "type":     "trans",
                    "callType": el.call_type,
                    "label":    el.label,
                    "startTs":  el.start_ts,
                    "endTs":    el.end_ts,
                    "seq":      el.seq,
                    "color":    el.color,
                    "hoverIn":  el.hover_in,
                    "hoverOut": el.hover_out,
                    "isInstant": el.is_instant,
                }
                if el.cpr_data:
                    _td["cprData"] = el.cpr_data
                if el.model:
                    _td["model"] = el.model
                if el.parallel_group_id:
                    _td["parallelGroupId"] = el.parallel_group_id
                    _td["parallelRank"]    = el.parallel_rank
                    _td["parallelSize"]    = el.parallel_size
                seq.append(_td)
        _lane_d: dict[str, Any] = {
            "laneId":   lane.lane_id,
            "level":    lane.level,
            "label":    lane.label,
            "sequence": seq,
        }
        if lane.parallel_spans:
            _lane_d["parallelSpans"] = lane.parallel_spans
        lanes_json.append(_lane_d)

    t_min_chart = all_buckets[0]  if all_buckets else 0.0
    t_max_chart = all_buckets[-1] if all_buckets else 0.0
    return {
        "title":            title,
        "widthMode":        width_mode,
        "buckets":          all_buckets,
        "sharedBuckets":    shared_buckets,
        "lanes":            lanes_json,
        "showUserActors":   show_user_actors,
        "tMin":             t_min_chart,
        "tMax":             t_max_chart,
        "showTimeAxis":     show_time_axis,
        "highlightAgents":  ann.get("highlight_agents") or [],
    }


_D3_TEMPLATE = Path(__file__).parent.parent / "assets" / "multilevel.html"


def _fmt_d3_html(data: dict) -> str:
    chart_json = json.dumps(data, ensure_ascii=False, default=str)
    tmpl = _D3_TEMPLATE.read_text(encoding="utf-8")
    return (
        tmpl
        .replace("{title}", _esc(data["title"]))
        .replace("{chart_json}", chart_json)
    )


def build_trajectory_chart_data(
    trace: "Union[str, Path, list[dict]]",
    title: str = "MAS Multilevel Trajectory",
    width_mode: str = "log",
    show_user_actors: bool = True,
    show_time_axis: bool = True,
    show_provenance: bool = True,
    annotations: dict | None = None,
) -> dict:
    """Build the chart data dict for the D3 multilevel renderer.

    This is the **data-preparation stage** of the pipeline — equivalent to
    the server side when the UI path is used.  The browser renders the chart
    via the D3 renderer already loaded in the ``<iframe>`` by calling
    ``iframe.contentWindow.masUpdateChart(data)`` or via ``postMessage``.

    Returns
    -------
    dict
        JSON-serialisable dict that the ``multilevel.html`` D3 renderer
        expects as ``const CHART = {...}``.  Pass it to :func:`_fmt_d3_html`
        to get a self-contained HTML page (pipeline / static path), or send
        it over WebSocket as ``{type: "viz_data", data: <this dict>}`` for
        the live UI path.

    Examples
    --------
    Pipeline (static)::

        data = build_trajectory_chart_data(events, title="My Trace")
        html = _fmt_d3_html(data)   # → self-contained HTML artifact

    UI / WebSocket (live)::

        # Server
        data = build_trajectory_chart_data(events_list, title="My Trace")
        await ws.send_json({"type": "viz_data", "pane_id": "trace-traj", "data": data})

        # Browser (multilevel.html postMessage listener)
        iframe.contentWindow.postMessage({type: "mas_chart_update", data: data}, "*")
        # → masUpdateChart(data) re-renders the chart in-place
    """
    if not isinstance(trace, list):
        trace = load_trace(trace)
    if not trace:
        return {}
    records = _build_call_records(trace)
    if not records:
        return {}
    state_reg, lanes = _build_dag(records, trace, show_provenance=show_provenance)
    if not lanes:
        return {}
    return _build_chart_data(
        state_reg, lanes,
        title=title,
        width_mode=width_mode,
        show_user_actors=show_user_actors,
        show_time_axis=show_time_axis,
        annotations=annotations,
        records=records,
    )


def build_trajectory_chart_data_from_kg(
    source: "Any",
    query: "Any | None" = None,
    title: str = "MAS Multilevel Trajectory",
    width_mode: str = "log",
    show_user_actors: bool = True,
    show_time_axis: bool = True,
    show_provenance: bool = True,
) -> dict:
    """KG-backed variant of :func:`build_trajectory_chart_data`.

    Used by the WebSocket handler ``_handle_kg_viz`` to compute the chart
    data dict that is sent to the browser as ``{type: "viz_data", data: ...}``.
    The browser's ``masUpdateChart(data)`` re-renders the D3 chart in-place
    without reloading D3 from CDN.

    Parameters
    ----------
    source:
        :class:`~mas.lab.plots.kg_adapter.KGSource` instance, ``dict`` (raw
        KG), or ``str``/``Path`` (kg.json file path).
    query:
        Optional :class:`~mas.lab.plots.kg_adapter.FacetQuery`.
    """
    from mas.lab.plots.kg_adapter import KGSource, FacetQuery as _FQ

    if isinstance(source, (str, Path, dict)):
        src = KGSource(source) if isinstance(source, dict) else KGSource.from_file(source)
    else:
        src = source

    q = FacetQuery.from_dict(query) if isinstance(query, dict) else query  # type: ignore[assignment]
    records, events = src.load(q)
    if not records:
        return {}
    state_reg, lanes = _build_dag(records, events, show_provenance=show_provenance)
    if not lanes:
        return {}
    return _build_chart_data(
        state_reg, lanes,
        title=title,
        width_mode=width_mode,
        show_user_actors=show_user_actors,
        show_time_axis=show_time_axis,
        records=records,
    )
