#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Mermaid and table formatters."""

from mas.lab.plots.trajectory.extract import _short_task

# Formatters
# ---------------------------------------------------------------------------

def _fmt_mermaid(delegations: list[dict], agents: list[str], include_prompts: bool) -> str:
    """Render a Mermaid sequenceDiagram."""
    lines = ["sequenceDiagram"]
    for agent in agents:
        if agent == "User":
            lines.append(f"    actor {agent}")
        else:
            lines.append(f"    participant {agent}")
    lines.append("")

    for i, d in enumerate(delegations, 1):
        src = d["source"]
        tgt = d["target"]
        status = d["status"]
        cid_short = d["correlation_id"][:8] if d["correlation_id"] else f"#{i}"

        if d.get("fwd_only"):
            # User → entry-agent: only the forward request arrow
            label = _short_task(d["task"]) if include_prompts and d["task"] else f"[{cid_short}]"
            lines.append(f"    {src}->>{tgt}: {label}")
            continue

        if d.get("ret_only"):
            # entry-agent → User: only the return answer arrow, placed last
            label = (_short_task(d["output"], max_chars=80)
                     if include_prompts and d.get("output") else "response")
            lines.append(f"    {src}-->>{tgt}: {label}")
            continue

        hl = d.get("highlighted", False)

        if include_prompts and d["task"]:
            label = _short_task(d["task"])
            lines.append(f"    {src}->>+{tgt}: [{cid_short}] {label}")
        else:
            lines.append(f"    {src}->>+{tgt}: delegate [{cid_short}]")

        if hl:
            lines.append(f"    Note over {src},{tgt}: ⚠️ highlighted")

        result_arrow = "-->>" if status == "success" else "--x"
        if include_prompts and d.get("output"):
            out_label = _short_task(d["output"], max_chars=70)
            lines.append(f"    {tgt}{result_arrow}-{src}: {out_label}")
        else:
            lines.append(f"    {tgt}{result_arrow}-{src}: {status} [{cid_short}]")

    return "\n".join(lines)


def _fmt_table(delegations: list[dict], include_prompts: bool) -> str:
    """Render a plain-text table."""
    if not delegations:
        return "(no delegation events found)"

    col_w = {"#": 3, "from": 14, "to": 14, "status": 8, "dur_ms": 7, "corr": 10}
    if include_prompts:
        col_w["task"] = 50
        col_w["output"] = 55

    # header
    hdr_parts = {k: k.center(v) for k, v in col_w.items()}
    sep = "+" + "+".join("-" * (v + 2) for v in col_w.values()) + "+"
    hdr = "|" + "|".join(f" {v} " for v in hdr_parts.values()) + "|"

    rows = [sep, hdr, sep]
    for i, d in enumerate(delegations, 1):
        dur = int((d["ts_end"] - d["ts_start"]) * 1000) if d["ts_end"] else 0
        row: dict[str, str] = {
            "#": str(i).center(col_w["#"]),
            "from": d["source"].ljust(col_w["from"])[:col_w["from"]],
            "to": d["target"].ljust(col_w["to"])[:col_w["to"]],
            "status": d["status"].ljust(col_w["status"])[:col_w["status"]],
            "dur_ms": str(dur).rjust(col_w["dur_ms"]),
            "corr": d["correlation_id"][:col_w["corr"]].ljust(col_w["corr"]),
        }
        if include_prompts:
            task_short = (_short_task(d["task"], col_w["task"] - 2)
                          if d["task"] else "")
            row["task"] = task_short.ljust(col_w["task"])[:col_w["task"]]
            out_short = (_short_task(d.get("output", ""), col_w["output"] - 2)
                         if d.get("output") else "")
            row["output"] = out_short.ljust(col_w["output"])[:col_w["output"]]
        rows.append("|" + "|".join(f" {v} " for v in row.values()) + "|")

    rows.append(sep)
    return "\n".join(rows)
