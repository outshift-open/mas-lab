# KG Comparison Module — Reference & Examples

**Module:** `mas.library.kg.core.compare`  
**Top-level import:** `from mas.library.kg import compare_kg, KGCompareResult`

---

## Overview

The KG comparison module provides structural regression testing for knowledge graphs
produced by multi-agent systems (MAS). Given two `kg.jsonld` documents — a *candidate*
produced by the system under test and a *reference* representing the expected ground
truth — `compare_kg` runs seven checks and returns a single `KGCompareResult` that
captures overall pass/fail, per-check detail, and graph statistics for both sides.

### When to use this module

**Regression testing between runs.** After refactoring a MAS pipeline, verify that
the new KG is structurally equivalent to a stored golden reference. IDs and timestamps
change on every run and are automatically excluded from comparison; the checks focus on
structural properties that should remain stable.

**CI parity gate.** Serialize a reference KG from a known-good run and commit it to
your repository. Add a CI step that calls `compare_kg` on each new run and asserts
`result.passed is True`. Any structural regression (missing agents, dropped tools,
shallower call depth) fails the build.

**Evaluating a new MAS implementation.** When replacing one framework backend with
another, use the golden KG from the old implementation as the reference and run
`compare_kg` against the new implementation's output to confirm behavioral parity
before shipping.

### What "structural" means

The comparison operates on the graph topology, agent set, tool set, node type
distribution, edge type distribution, delegation patterns, and element-level identity
(type + stable fields). It deliberately ignores run-specific volatile fields: all
span/trace/session/call identifiers, timestamps, and durations. See
[Volatile fields](#volatile-fields) for the complete list.

---

## `compare_kg` — full reference

### Signature

```python
def compare_kg(
    candidate: dict,
    reference: dict,
    *,
    strict: bool = False,
) -> KGCompareResult:
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `candidate` | `dict` | KG document produced by the system under test. Must have `"nodes"` and `"edges"` keys (lists of dicts). Missing keys are treated as empty lists. |
| `reference` | `dict` | Ground-truth KG. Same format as `candidate`. |
| `strict` | `bool` | When `True`, check 7 (`element_level_diff`) is included in the pass/fail decision. Default `False`: only checks 1–6 determine `KGCompareResult.passed`. |

### Return value

A `KGCompareResult` dataclass. See [KGCompareResult](#kgcompareresult) below.

### Checks performed

| # | Name | What it tests |
|---|------|---------------|
| 1 | `agent_coverage` | Candidate contains every agent ID present in reference |
| 2 | `node_distribution` | Candidate has ≥ reference count for each node type |
| 3 | `edge_distribution` | Candidate has ≥ reference count for each edge type |
| 4 | `call_depth` | Candidate's max containment nesting depth ≥ reference |
| 5 | `tool_coverage` | Candidate contains every tool name present in reference |
| 6 | `delegation_topology` | All agent-to-agent delegation pairs from reference appear in candidate |
| 7 | `element_level_diff` | Node-by-node and edge-by-edge diff (volatile fields excluded) |

Checks 1–6 always count toward `passed`. Check 7 only counts when `strict=True`.

---

### Example: basic comparison

```python
import json
from mas.library.kg import compare_kg

with open("golden.kg.jsonld") as f:
    reference = json.load(f)

with open("run_output.kg.jsonld") as f:
    candidate = json.load(f)

result = compare_kg(candidate, reference)

print(f"Passed: {result.passed}")
print(f"Summary: {result.summary}")
# Passed: True
# Summary: {'total_checks': 7, 'passed': 7, 'failed': 0}
```

---

### Example: CI assertion

Use `assert` (or your test framework's equivalent) to fail a CI build on structural
regression:

```python
import json
import pytest
from mas.library.kg import compare_kg


def load_kg(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def test_kg_parity():
    reference = load_kg("tests/fixtures/golden.kg.jsonld")
    candidate = load_kg("artifacts/latest_run.kg.jsonld")

    result = compare_kg(candidate, reference)

    failed_checks = [c for c in result.checks if not c["passed"]]
    assert result.passed, (
        f"KG comparison failed {result.summary['failed']}/7 checks:\n"
        + "\n".join(f"  - {c['name']}: {c}" for c in failed_checks)
    )
```

Run with strict mode to also gate on exact element-level equivalence:

```python
def test_kg_parity_strict():
    reference = load_kg("tests/fixtures/golden.kg.jsonld")
    candidate = load_kg("artifacts/latest_run.kg.jsonld")

    result = compare_kg(candidate, reference, strict=True)
    assert result.passed, result.to_dict()
```

---

### Example: saving a report to disk

```python
import json
from mas.library.kg import compare_kg

reference = json.load(open("golden.kg.jsonld"))
candidate = json.load(open("candidate.kg.jsonld"))

result = compare_kg(candidate, reference, strict=True)

report_path = "compare_report.json"
with open(report_path, "w") as f:
    json.dump(result.to_dict(), f, indent=2)

print(f"Report saved to {report_path}")
print(f"Overall: {'PASS' if result.passed else 'FAIL'}")
print(f"Checks passed: {result.summary['passed']}/{result.summary['total_checks']}")
```

---

## `KGCompareResult`

```python
@dataclass
class KGCompareResult:
    passed: bool
    checks: list[dict]
    summary: dict
    reference_stats: dict
    candidate_stats: dict

    def to_dict(self) -> dict: ...
```

### Fields

#### `passed: bool`

`True` when all checks that count toward pass/fail passed.  
- In default mode (`strict=False`): checks 1–6 must all pass.  
- In strict mode (`strict=True`): all 7 checks must pass.

#### `checks: list[dict]`

One dict per check, in the order checks were run (1–7). Every dict contains at minimum:

```python
{
    "name": str,    # check name, e.g. "agent_coverage"
    "passed": bool,
}
```

Additional keys are check-specific. See [Individual check functions](#individual-check-functions)
for the full dict shape of each check.

#### `summary: dict`

```python
{
    "total_checks": 7,
    "passed": int,   # number of checks that passed (always 0–7)
    "failed": int,   # number of checks that failed (always 0–7)
}
```

Note: `summary` counts all 7 checks regardless of `strict`. The `passed` field on the
result uses only the relevant subset.

#### `reference_stats: dict`

```python
{
    "nodes": int,         # total node count in reference
    "edges": int,         # total edge count in reference
    "agents": list[str],  # sorted list of unique agent IDs
}
```

#### `candidate_stats: dict`

Same structure as `reference_stats`, for the candidate graph.

#### `.to_dict() -> dict`

Returns a fully JSON-serializable dict containing all five fields. Suitable for
logging, storing in a database, or writing to disk.

---

### Example: iterating and printing checks

```python
from mas.library.kg import compare_kg

result = compare_kg(candidate, reference)

for check in result.checks:
    status = "PASS" if check["passed"] else "FAIL"
    print(f"[{status}] {check['name']}")

# [PASS] agent_coverage
# [PASS] node_distribution
# [FAIL] edge_distribution
# [PASS] call_depth
# [PASS] tool_coverage
# [PASS] delegation_topology
# [PASS] element_level_diff
```

Print details only for failing checks:

```python
for check in result.checks:
    if not check["passed"]:
        print(f"\n--- FAILED: {check['name']} ---")
        for key, value in check.items():
            if key not in ("name", "passed"):
                print(f"  {key}: {value}")
```

Access a specific check by name:

```python
checks_by_name = {c["name"]: c for c in result.checks}
edge_check = checks_by_name["edge_distribution"]
if not edge_check["passed"]:
    print("Edge type deficits:", edge_check["deficits"])
```

---

## Individual check functions

All seven check functions are importable directly from the module:

```python
from mas.library.kg.core.compare import (
    check_agent_coverage,
    check_node_distribution,
    check_edge_distribution,
    check_call_depth,
    check_tool_coverage,
    check_delegation_topology,
    check_element_diff,
)
```

All functions accept nodes and/or edges as plain lists of dicts. Edges may use either
`from_id`/`to_id` or `source`/`target` field names — both formats are recognized.

---

### Check 1: `check_agent_coverage`

```python
def check_agent_coverage(
    candidate_nodes: list[dict],
    reference_nodes: list[dict],
) -> dict:
```

**What it tests.** Extracts the set of agent IDs from both graphs (via `agentId` or
`agent_id` field on any node) and verifies that every agent ID in the reference also
appears in the candidate.

**Pass condition.** `missing` is empty — the candidate contains all reference agent IDs.
Extra agents in the candidate do not cause failure.

**Result dict shape:**

```python
{
    "name": "agent_coverage",
    "passed": bool,
    "reference_agents": ["orchestrator", "planner", "executor"],
    "candidate_agents": ["executor", "orchestrator", "planner", "reviewer"],
    "missing": [],          # agents in reference but not in candidate
    "extra":   ["reviewer"] # agents in candidate but not in reference (informational)
}
```

**Example with failure:**

```python
{
    "name": "agent_coverage",
    "passed": False,
    "reference_agents": ["orchestrator", "planner", "executor"],
    "candidate_agents": ["orchestrator", "executor"],
    "missing": ["planner"],
    "extra": []
}
```

---

### Check 2: `check_node_distribution`

```python
def check_node_distribution(
    candidate_nodes: list[dict],
    reference_nodes: list[dict],
) -> dict:
```

**What it tests.** Counts nodes by type (`nodeType`, `node_type`, or `type` field) in
both graphs and checks that the candidate has at least as many nodes of each type as the
reference.

**Pass condition.** `deficits` is empty — for every node type in the reference, the
candidate count is ≥ the reference count.

**Result dict shape:**

```python
{
    "name": "node_distribution",
    "passed": bool,
    "reference": {"AgentCall": 3, "ToolCall": 8, "LLMCall": 3},
    "candidate": {"AgentCall": 4, "ToolCall": 8, "LLMCall": 2},
    "deficits":  {"LLMCall": 1}  # shortfall per type; empty when passed
}
```

The `deficits` value for each type is `reference_count - candidate_count`.

---

### Check 3: `check_edge_distribution`

```python
def check_edge_distribution(
    candidate_edges: list[dict],
    reference_edges: list[dict],
) -> dict:
```

**What it tests.** Mirrors check 2 for edges. Counts edges by type (`edgeType`,
`edge_type`, or `type` field) and checks that the candidate has at least as many edges
of each type as the reference.

**Pass condition.** `deficits` is empty.

**Result dict shape:**

```python
{
    "name": "edge_distribution",
    "passed": bool,
    "reference": {"contains": 10, "callsAgent": 2, "invokes": 8},
    "candidate": {"contains": 10, "callsAgent": 2, "invokes": 7},
    "deficits":  {"invokes": 1}
}
```

---

### Check 4: `check_call_depth`

```python
def check_call_depth(
    candidate_nodes: list[dict],
    candidate_edges: list[dict],
    reference_nodes: list[dict],
    reference_edges: list[dict],
) -> dict:
```

**What it tests.** Computes the maximum containment nesting depth in both graphs by
traversing `contains` and `hasCall` edges. This reflects how deeply nested the call
hierarchy is — a shallow candidate suggests truncated or missing sub-calls.

**Pass condition.** `candidate_depth >= reference_depth`.

**Result dict shape:**

```python
{
    "name": "call_depth",
    "passed": bool,
    "reference_depth": 4,
    "candidate_depth": 4,
}
```

**Example with failure:**

```python
{
    "name": "call_depth",
    "passed": False,
    "reference_depth": 4,
    "candidate_depth": 2,
}
```

---

### Check 5: `check_tool_coverage`

```python
def check_tool_coverage(
    candidate_nodes: list[dict],
    reference_nodes: list[dict],
) -> dict:
```

**What it tests.** Collects tool names from nodes of type `ToolCall` (via `toolName` or
`tool_name` field) in both graphs. Verifies every tool present in the reference also
appears in the candidate.

**Pass condition.** `missing` is empty.

**Result dict shape:**

```python
{
    "name": "tool_coverage",
    "passed": bool,
    "reference_tools": ["file_search", "python_interpreter", "web_search"],
    "candidate_tools": ["file_search", "python_interpreter", "web_search"],
    "missing": []
}
```

**Example with failure:**

```python
{
    "name": "tool_coverage",
    "passed": False,
    "reference_tools": ["file_search", "python_interpreter", "web_search"],
    "candidate_tools": ["file_search", "web_search"],
    "missing": ["python_interpreter"]
}
```

---

### Check 6: `check_delegation_topology`

```python
def check_delegation_topology(
    candidate_nodes: list[dict],
    candidate_edges: list[dict],
    reference_nodes: list[dict],
    reference_edges: list[dict],
) -> dict:
```

**What it tests.** Extracts agent-to-agent delegation pairs by finding edges of type
`callsAgent` or `delegates_to`, then resolving source and target node IDs to agent IDs
via the `agentId`/`agent_id` field on nodes. Checks that every delegation pair in the
reference appears in the candidate.

**Pass condition.** `missing` is empty.

**Result dict shape:**

```python
{
    "name": "delegation_topology",
    "passed": bool,
    "reference": ["orchestrator→executor", "orchestrator→planner"],
    "candidate": ["orchestrator→executor", "orchestrator→planner", "planner→executor"],
    "missing":   []
}
```

Pairs are formatted as `"source_agent→target_agent"` strings. Self-loops (same agent on
both sides) are excluded.

**Example with failure:**

```python
{
    "name": "delegation_topology",
    "passed": False,
    "reference": ["orchestrator→executor", "orchestrator→planner"],
    "candidate": ["orchestrator→executor"],
    "missing":   ["orchestrator→planner"]
}
```

---

### Check 7: `check_element_diff`

```python
def check_element_diff(
    candidate_nodes: list[dict],
    candidate_edges: list[dict],
    reference_nodes: list[dict],
    reference_edges: list[dict],
) -> dict:
```

**What it tests.** A node-by-node and edge-by-edge structural diff. Each node is
identified by a stable key: `nodeType|agentId|toolName`. Each edge is identified by
`edgeType|source_id|target_id`. All volatile fields (IDs, timestamps, durations) are
excluded before keying.

Nodes or edges in the reference that have no matching key in the candidate appear in
`missing_nodes`/`missing_edges`. Elements in the candidate with no reference counterpart
appear in `spurious_nodes`/`spurious_edges`.

**Pass condition.** All four lists (`missing_nodes`, `spurious_nodes`, `missing_edges`,
`spurious_edges`) are empty.

**Important:** this check is **not included in pass/fail by default**. It is included
only when `strict=True` is passed to `compare_kg`. You can still run it independently
or inspect its result from `KGCompareResult.checks` regardless of strict mode.

**Result dict shape:**

```python
{
    "name": "element_level_diff",
    "passed": bool,
    "missing_nodes":  ["LLMCall|orchestrator|"],    # in reference, not in candidate
    "spurious_nodes": [],                            # in candidate, not in reference
    "missing_edges":  [],
    "spurious_edges": ["invokes|node-42|node-99"],  # unexpected edge in candidate
}
```

**Example when identical:**

```python
{
    "name": "element_level_diff",
    "passed": True,
    "missing_nodes":  [],
    "spurious_nodes": [],
    "missing_edges":  [],
    "spurious_edges": [],
}
```

---

## Strict mode

By default, `compare_kg` determines `KGCompareResult.passed` from checks 1–6 only.
Check 7 (`element_level_diff`) is always run and always appears in `result.checks`, but
a failure there does not set `passed = False` unless `strict=True`.

**When to use default mode.** Regression suites that tolerate minor graph variations —
extra context nodes, diagnostic annotations, or framework-specific auxiliary edges —
should use default mode. Structural shape (agent set, tool set, delegation, depth) is
enforced; exact element identity is not.

**When to use strict mode.** Golden-file parity tests where the candidate must be
byte-for-byte structurally identical to the reference (minus volatile fields). Use this
when validating a deterministic pipeline where no structural variation is expected.

```python
# Default: checks 1–6 govern pass/fail
result = compare_kg(candidate, reference)
assert result.passed

# Strict: all 7 checks govern pass/fail
result = compare_kg(candidate, reference, strict=True)
assert result.passed
```

You can also check strict-mode independently of how compare_kg was called:

```python
result = compare_kg(candidate, reference)  # strict=False

# Manually inspect element diff without strict mode affecting result.passed
diff = next(c for c in result.checks if c["name"] == "element_level_diff")
if not diff["passed"]:
    print("Element diff detected (informational):")
    print("  Missing nodes:", diff["missing_nodes"])
    print("  Spurious nodes:", diff["spurious_nodes"])
```

---

## Using individual checks

Import and call any check function directly without going through `compare_kg`. This is
useful in custom evaluation loops, Jupyter notebooks, or when you only care about one
dimension of comparison.

```python
from mas.library.kg.core.compare import check_tool_coverage

candidate_nodes = kg_candidate["nodes"]
reference_nodes = kg_reference["nodes"]

result = check_tool_coverage(candidate_nodes, reference_nodes)

if not result["passed"]:
    print(f"Missing tools: {result['missing']}")
```

```python
from mas.library.kg.core.compare import check_delegation_topology

topo = check_delegation_topology(
    candidate["nodes"], candidate["edges"],
    reference["nodes"], reference["edges"],
)
print("Reference delegation pairs:", topo["reference"])
print("Missing from candidate:", topo["missing"])
```

All functions accept raw lists of dicts and return plain dicts — no library objects
required.

---

## Volatile fields

The following fields are stripped from node and edge dicts before any identity-based
comparison (check 7 and the stable key computation used in check 6). Checks 1–5 do not
do field-level comparison and are unaffected.

**Run-specific identifiers:**

| Field | Also accepted as |
|-------|-----------------|
| `id` | — |
| `callId` | `call_id` |
| `parentCallId` | `parent_call_id` |
| `spanId` | `span_id` |
| `traceId` | `trace_id` |
| `sourceRecordIds` | — |
| `runId` | `run_id` |
| `sessionId` | `session_id` |
| `executionId` | — |
| `sourceCallId` | — |
| `stateNodeId` | — |
| `fromState` | — |
| `toState` | — |
| `annotationId` | — |
| `transitionId` | — |
| `realizesCallId` | — |
| `contentHash` | — |

**Timestamps and durations:**

| Field | Also accepted as |
|-------|-----------------|
| `timestamp` | — |
| `startTime` | `start_time` |
| `endTime` | `end_time` |
| `durationMs` | `duration_ms` |
| `transitionTimestamp` | — |
| `transitionDuration` | — |

**Token counts and segments:**

| Field | Notes |
|-------|-------|
| `segments` | Raw LLM message segments (variable per run) |
| `totalTokens` | Token count (may vary with model version) |

Any field not in this list is treated as stable and participates in identity comparison.
If your graph contains additional run-specific fields not listed here, strip them before
calling `compare_kg` or use default mode (strict=False) to avoid spurious diff failures.

---

## Quick reference

```python
# Full comparison (default mode)
from mas.library.kg import compare_kg, KGCompareResult
result: KGCompareResult = compare_kg(candidate_kg, reference_kg)

# Full comparison (strict mode — check 7 counts toward pass/fail)
result = compare_kg(candidate_kg, reference_kg, strict=True)

# Key result attributes
result.passed                # bool
result.checks                # list of 7 dicts
result.summary               # {"total_checks": 7, "passed": N, "failed": N}
result.reference_stats       # {"nodes": N, "edges": N, "agents": [...]}
result.candidate_stats       # {"nodes": N, "edges": N, "agents": [...]}
result.to_dict()             # fully serializable dict of all of the above

# Individual checks (from mas.library.kg.core.compare)
check_agent_coverage(cand_nodes, ref_nodes)
check_node_distribution(cand_nodes, ref_nodes)
check_edge_distribution(cand_edges, ref_edges)
check_call_depth(cand_nodes, cand_edges, ref_nodes, ref_edges)
check_tool_coverage(cand_nodes, ref_nodes)
check_delegation_topology(cand_nodes, cand_edges, ref_nodes, ref_edges)
check_element_diff(cand_nodes, cand_edges, ref_nodes, ref_edges)
```
