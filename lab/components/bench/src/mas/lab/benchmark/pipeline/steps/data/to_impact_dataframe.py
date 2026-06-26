#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""ToImpactDataFrameStep — assemble the impact assessment DataFrame.

Joins KG structure (States, Transitions, Calls) with embeddings and metrics
into a single tidy DataFrame. This is the input for impact assessment inference.

The DataFrame schema follows the lab impact ontology:
    - Rows: one per State in the trajectory
    - Columns: state metadata + embedding vector + associated metrics

Output::

    {output_dir}/impact_assessment.parquet
    {output_dir}/impact_assessment.csv   (optional, for inspection)

DataFrame columns::

    run_id            str     Run identifier
    state_id          str     State node ID
    call_id           str     Source call ID (AgentCall/LLMCall/ToolCall)
    call_type         str     Node type of the source call
    agent_id          str     Agent that produced this state
    semantic_type     str     "initial" | "final"
    content           str     State content (truncated)
    embedding         list    Vector embedding (or NaN if missing)
    transition_to     str     ID of the State this transitions to
    <metric_name>     float   One column per metric value

Config keys::

    include_embedding: bool   Include full embedding vectors (default: true)
    include_content:   bool   Include state text content (default: true)
    max_content:       int    Max content chars in DF (default: 500)
    output_format:     str    "parquet" | "csv" | "both" (default: "both")
"""

import json
import logging
from pathlib import Path
from typing import Any

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class ToImpactDataFrameStep(PipelineStep):
    """Assemble KG States + embeddings + metrics into impact assessment DF."""

    type = "to_impact_dataframe"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        bench_dir = ctx.output_dir
        kg_path = bench_dir / "kg.json"
        states_emb_path = bench_dir / "embeddings" / "states.jsonl"
        metrics_path = bench_dir / "metrics.json"

        include_embedding = self.config.get("include_embedding", True)
        include_content = self.config.get("include_content", True)
        max_content = int(self.config.get("max_content", 500))
        output_format = self.config.get("output_format", "both")

        if not kg_path.exists():
            logger.error("kg.json not found — run normalize_events first")
            return StepOutput(metadata={"rows": 0})

        # ── Load KG ──────────────────────────────────────────────────────
        kg = json.loads(kg_path.read_text(encoding="utf-8"))
        nodes = kg.get("nodes", [])
        edges = kg.get("edges", [])
        run_id = kg.get("run_id", "")

        # Build lookup tables
        nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}

        # States
        states = [n for n in nodes if n.get("node_type") == "State"]
        if not states:
            logger.warning("ToImpactDF: no State nodes in kg.json")
            return StepOutput(metadata={"rows": 0})

        # Calls (AgentCall, LLMCall, ToolCall, ProcessingCall)
        call_types = {"AgentCall", "LLMCall", "ToolCall", "ProcessingCall"}
        calls_by_id: dict[str, dict] = {
            n["id"]: n for n in nodes if n.get("node_type") in call_types
        }

        # Agent lookup: call_id → agent_id (via "executedBy" edges)
        call_to_agent: dict[str, str] = {}
        for edge in edges:
            if edge.get("edge_type") == "executedBy":
                call_to_agent[edge["from_id"]] = edge["to_id"]

        # Transition edges: state → next state (via "leadsTo")
        state_transitions: dict[str, str] = {}
        for edge in edges:
            if edge.get("edge_type") == "leadsTo":
                state_transitions[edge["from_id"]] = edge["to_id"]

        # ── Load State embeddings ─────────────────────────────────────────
        embeddings_by_state: dict[str, list[float]] = {}
        if states_emb_path.exists():
            for line in states_emb_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    embeddings_by_state[rec["state_id"]] = rec["vector"]
        else:
            logger.warning("ToImpactDF: embeddings/states.jsonl not found — DF will lack embeddings")

        # ── Load metrics ──────────────────────────────────────────────────
        # metrics.json has { "session": { metric_name: {value, reasoning, error} } }
        session_metrics: dict[str, float] = {}
        if metrics_path.exists():
            try:
                doc = json.loads(metrics_path.read_text(encoding="utf-8"))
                for metric_name, metric_data in doc.get("session", {}).items():
                    if isinstance(metric_data, dict) and metric_data.get("value") is not None:
                        session_metrics[metric_name] = metric_data["value"]
            except (json.JSONDecodeError, OSError):
                logger.debug('suppressed', exc_info=True)

        # ── Build DataFrame rows ──────────────────────────────────────────
        rows: list[dict[str, Any]] = []
        for state in states:
            state_id = state.get("id", state.get("stateNodeId", ""))
            call_id = state.get("sourceCallId", "")
            call_node = calls_by_id.get(call_id, {})

            row: dict[str, Any] = {
                "run_id": run_id,
                "state_id": state_id,
                "call_id": call_id,
                "call_type": call_node.get("node_type", ""),
                "agent_id": call_to_agent.get(call_id, call_node.get("agentId", "")),
                "semantic_type": state.get("semanticType", ""),
                "transition_to": state_transitions.get(state_id, ""),
            }

            if include_content:
                row["content"] = state.get("content", "")[:max_content]

            if include_embedding:
                row["embedding"] = embeddings_by_state.get(state_id)

            # Attach metrics (session-level for now; per-call when available)
            for metric_name, value in session_metrics.items():
                row[metric_name] = value

            rows.append(row)

        # ── Write output ──────────────────────────────────────────────────
        output_files: list[Path] = []

        if output_format in ("parquet", "both"):
            parquet_path = bench_dir / "impact_assessment.parquet"
            try:
                import pandas as pd
                df = pd.DataFrame(rows)
                df.to_parquet(parquet_path, index=False)
                output_files.append(parquet_path)
                logger.info("ToImpactDF: wrote %s (%d rows)", parquet_path, len(rows))
            except ImportError:
                logger.warning("pandas not available — falling back to CSV only")
                output_format = "csv"

        if output_format in ("csv", "both"):
            csv_path = bench_dir / "impact_assessment.csv"
            try:
                import pandas as pd
                df = pd.DataFrame(rows)
                # Drop embedding column for CSV (too large)
                csv_cols = [c for c in df.columns if c != "embedding"]
                df[csv_cols].to_csv(csv_path, index=False)
                output_files.append(csv_path)
            except ImportError:
                # Fallback: write CSV without pandas
                import csv as csv_mod
                csv_path = bench_dir / "impact_assessment.csv"
                cols = [c for c in rows[0].keys() if c != "embedding"] if rows else []
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv_mod.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                output_files.append(csv_path)

        logger.info("ToImpactDF done: %d states, %d with embeddings, %d metrics",
                    len(rows), sum(1 for r in rows if r.get("embedding")), len(session_metrics))

        return StepOutput(
            data={"rows": len(rows), "metrics": list(session_metrics.keys())},
            files=output_files,
            metadata={
                "total_states": len(rows),
                "embedded_states": sum(1 for r in rows if r.get("embedding")),
                "metric_columns": list(session_metrics.keys()),
            },
        )
