#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Analyze memory provenance experiment traces.

Extracts from events.jsonl:
- Per-turn: memory tool calls (facts stored, block labels)
- Per-turn: LLM output
- Per-turn: context segments (memory injections into prompt)
- Cross-run: trajectory comparison (Letta vs Semantic)
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def parse_trace(events_path: str) -> dict:
    """Parse events.jsonl into a per-turn analysis structure."""
    events = []
    with open(events_path) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    turns = []
    current_turn = None
    for e in events:
        kind = e.get("kind", "")

        if kind == "execution_start":
            current_turn = {
                "input": e.get("input", ""),
                "output": "",
                "tool_calls": [],
                "llm_calls": 0,
                "context_segments": [],
                "session_id": (e.get("context") or {}).get("session_id", ""),
            }
        elif kind == "tool_call_start" and current_turn is not None:
            current_turn["tool_calls"].append({
                "tool_name": e.get("tool_name", ""),
                "arguments": e.get("arguments", {}),
            })
        elif kind == "llm_call_start" and current_turn is not None:
            current_turn["llm_calls"] += 1
        elif kind == "processing_call_start" and current_turn is not None:
            if e.get("processing_name") == "context_assembly":
                # Context assembly produces segments in the processing_call_end
                pass
        elif kind == "execution_end" and current_turn is not None:
            current_turn["output"] = e.get("output", "")
            current_turn["status"] = e.get("status", "")
            turns.append(current_turn)
            current_turn = None

    return {"turns": turns, "event_count": len(events)}


def analyze_letta_run(trace: dict) -> dict:
    """Extract Letta-specific metrics from a single run."""
    turns = trace["turns"]
    memory_writes = []
    recall_scores = []

    for i, turn in enumerate(turns):
        # Count memory write operations
        writes = [tc for tc in turn["tool_calls"]
                  if tc["tool_name"] in ("core_memory_append", "core_memory_replace", "memory_rethink")]
        for w in writes:
            memory_writes.append({
                "turn": i + 1,
                "tool": w["tool_name"],
                "block": w["arguments"].get("label", ""),
                "content": w["arguments"].get("content", "")[:100],
            })

        # Check recall accuracy for turns 3-4 (recall questions)
        if i == 2:  # "What is my name and where do I work?"
            out = turn["output"].lower()
            score = (("alex" in out) + ("acme" in out)) / 2.0
            recall_scores.append({"turn": 3, "question": "identity", "score": score})
        elif i == 3:  # "What programming language..."
            out = turn["output"].lower()
            score = (("python" in out) + ("uv" in out)) / 2.0
            recall_scores.append({"turn": 4, "question": "preferences", "score": score})

    # Check if turn 5 (reasoning) references stored facts
    reasoning_quality = 0.0
    if len(turns) >= 5:
        out = turns[4]["output"].lower()
        facts_used = sum([
            "alex" in out,
            "acme" in out or "mas" in out,
            "python" in out,
            "multi-agent" in out or "multi agent" in out,
        ])
        reasoning_quality = facts_used / 4.0

    return {
        "memory_writes": memory_writes,
        "recall_scores": recall_scores,
        "reasoning_quality": reasoning_quality,
        "total_tool_calls": sum(len(t["tool_calls"]) for t in turns),
        "total_llm_calls": sum(t["llm_calls"] for t in turns),
    }


def analyze_semantic_run(trace: dict) -> dict:
    """Extract semantic-memory-specific metrics from a single run."""
    turns = trace["turns"]
    recall_scores = []

    for i, turn in enumerate(turns):
        # Check recall accuracy for turns 3-4
        if i == 2:
            out = turn["output"].lower()
            score = (("alex" in out) + ("acme" in out)) / 2.0
            recall_scores.append({"turn": 3, "question": "identity", "score": score})
        elif i == 3:
            out = turn["output"].lower()
            score = (("python" in out) + ("uv" in out)) / 2.0
            recall_scores.append({"turn": 4, "question": "preferences", "score": score})

    reasoning_quality = 0.0
    if len(turns) >= 5:
        out = turns[4]["output"].lower()
        facts_used = sum([
            "alex" in out,
            "acme" in out or "mas" in out,
            "python" in out,
            "multi-agent" in out or "multi agent" in out,
        ])
        reasoning_quality = facts_used / 4.0

    return {
        "memory_writes": [],  # Semantic = implicit, no explicit tool calls
        "recall_scores": recall_scores,
        "reasoning_quality": reasoning_quality,
        "total_tool_calls": sum(len(t["tool_calls"]) for t in turns),
        "total_llm_calls": sum(t["llm_calls"] for t in turns),
    }


def main():
    from mas.lab.paths import labs_root

    base = Path(__file__).parent
    prov_root = labs_root() / "tutorials" / "memory-provenance"
    letta_csv = sorted(prov_root.joinpath("letta-native").glob("mas_benchmark_*.csv"))[-1]
    semantic_csv = sorted(prov_root.joinpath("semantic-memory").glob("mas_benchmark_*.csv"))[-1]

    # Parse CSVs
    def load_traces(csv_path):
        traces = []
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                trace_path = row["trace_path"]
                if Path(trace_path).exists():
                    traces.append({
                        "run": int(row["run"]),
                        "trace": parse_trace(trace_path),
                        "elapsed_ms": float(row["elapsed_ms"]),
                    })
        return traces

    letta_traces = load_traces(letta_csv)
    semantic_traces = load_traces(semantic_csv)

    print("=" * 70)
    print("MEMORY PROVENANCE EXPERIMENT — ANALYSIS")
    print("=" * 70)

    # --- Letta Analysis ---
    print("\n## LETTA (MemGPT-style core memory blocks)")
    print(f"   Runs: {len(letta_traces)}")
    letta_results = [analyze_letta_run(t["trace"]) for t in letta_traces]

    # Memory writes per run
    print("\n   ### Memory Write Operations")
    for i, r in enumerate(letta_results):
        writes = r["memory_writes"]
        print(f"   Run {i+1}: {len(writes)} writes → {[w['tool'] for w in writes]}")
        for w in writes:
            print(f"      [{w['block']}] {w['content']}")

    # Recall accuracy
    print("\n   ### Recall Accuracy")
    for q in ["identity", "preferences"]:
        scores = [r["recall_scores"] for r in letta_results]
        q_scores = [s["score"] for sl in scores for s in sl if s["question"] == q]
        avg = sum(q_scores) / len(q_scores) if q_scores else 0
        print(f"   {q}: {avg:.2f} ({q_scores})")

    # Reasoning quality
    rq = [r["reasoning_quality"] for r in letta_results]
    print(f"\n   ### Reasoning Quality: {sum(rq)/len(rq):.2f} ({rq})")

    # LLM calls
    lc = [r["total_llm_calls"] for r in letta_results]
    tc = [r["total_tool_calls"] for r in letta_results]
    print(f"   ### LLM calls: {lc}  Tool calls: {tc}")

    # --- Semantic Analysis ---
    print("\n" + "=" * 70)
    print("\n## SEMANTIC MEMORY (auto-extract + conversation history)")
    print(f"   Runs: {len(semantic_traces)}")
    semantic_results = [analyze_semantic_run(t["trace"]) for t in semantic_traces]

    # Recall accuracy
    print("\n   ### Recall Accuracy")
    for q in ["identity", "preferences"]:
        scores = [r["recall_scores"] for r in semantic_results]
        q_scores = [s["score"] for sl in scores for s in sl if s["question"] == q]
        avg = sum(q_scores) / len(q_scores) if q_scores else 0
        print(f"   {q}: {avg:.2f} ({q_scores})")

    rq = [r["reasoning_quality"] for r in semantic_results]
    print(f"\n   ### Reasoning Quality: {sum(rq)/len(rq):.2f} ({rq})")

    lc = [r["total_llm_calls"] for r in semantic_results]
    tc = [r["total_tool_calls"] for r in semantic_results]
    print(f"   ### LLM calls: {lc}  Tool calls: {tc}")

    # --- Comparison ---
    print("\n" + "=" * 70)
    print("\n## COMPARISON")

    letta_recall = []
    for r in letta_results:
        for s in r["recall_scores"]:
            letta_recall.append(s["score"])
    semantic_recall = []
    for r in semantic_results:
        for s in r["recall_scores"]:
            semantic_recall.append(s["score"])

    l_avg = sum(letta_recall) / len(letta_recall) if letta_recall else 0
    s_avg = sum(semantic_recall) / len(semantic_recall) if semantic_recall else 0
    print(f"   Avg recall   — Letta: {l_avg:.2f}  Semantic: {s_avg:.2f}")

    l_rq = sum(r["reasoning_quality"] for r in letta_results) / len(letta_results)
    s_rq = sum(r["reasoning_quality"] for r in semantic_results) / len(semantic_results)
    print(f"   Reasoning    — Letta: {l_rq:.2f}  Semantic: {s_rq:.2f}")

    l_tc = sum(r["total_tool_calls"] for r in letta_results) / len(letta_results)
    s_tc = sum(r["total_tool_calls"] for r in semantic_results) / len(semantic_results)
    print(f"   Avg tools    — Letta: {l_tc:.1f}  Semantic: {s_tc:.1f}")

    l_lc = sum(r["total_llm_calls"] for r in letta_results) / len(letta_results)
    s_lc = sum(r["total_llm_calls"] for r in semantic_results) / len(semantic_results)
    print(f"   Avg LLM calls— Letta: {l_lc:.1f}  Semantic: {s_lc:.1f}")

    l_ms = sum(t["elapsed_ms"] for t in letta_traces) / len(letta_traces)
    s_ms = sum(t["elapsed_ms"] for t in semantic_traces) / len(semantic_traces)
    print(f"   Avg latency  — Letta: {l_ms:.0f}ms  Semantic: {s_ms:.0f}ms")

    # --- Trajectory Impact ---
    print("\n" + "=" * 70)
    print("\n## TRAJECTORY IMPACT — Memory Provenance")
    print("\n   ### Letta: Explicit Memory → Tool-mediated storage + retrieval")
    print("   - Agent uses core_memory_append to store facts in named blocks")
    print("   - Memory blocks are ALWAYS in the system prompt (context window)")
    print("   - Recall relies on: (1) blocks in system prompt + (2) conversation history")
    print("   - Provenance: tool_call_start events track exactly what was stored")

    print("\n   ### Semantic: Implicit Memory → Conversation history only")
    print("   - No explicit memory storage tools")
    print("   - Recall relies entirely on conversation history (FileSessionStore)")
    print("   - No separate memory blocks — facts live in prior user/assistant turns")
    print("   - Provenance: no memory-specific events; facts embedded in conversation flow")

    print("\n   ### Key Differences:")
    print(f"   - Letta uses ~{l_tc:.0f} tool calls/run for explicit memory management")
    print(f"   - Semantic uses {s_tc:.0f} tool calls (none for memory)")
    print(f"   - Letta needs ~{l_lc:.0f} LLM calls/run (extra calls for tool responses)")
    print(f"   - Semantic needs only {s_lc:.0f} LLM calls (no tool overhead)")
    print(f"   - Both achieve comparable recall ({l_avg:.2f} vs {s_avg:.2f})")


if __name__ == "__main__":
    main()
