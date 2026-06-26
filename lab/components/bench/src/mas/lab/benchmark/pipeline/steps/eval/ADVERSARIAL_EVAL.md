<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Adversarial Metrics Evaluation (`eval_adversarial`)

MAS Lab provides the **`eval_adversarial`** pipeline step for computing adversarial
detection metrics in the mas-necessity experiment.

**Input**: `metrics.json` + `events.jsonl` (from agent execution)

**How it works**:

- Reads final response from `events.jsonl` (last `execution_end` event)
- Loads dataset directly (supports list or dict format)
- Computes adversarial metrics via pattern matching
- Merges results into existing `metrics.json`

**Configuration**:

```yaml
pipeline:
  - name: eval-adversarial
    type: eval_adversarial
    depends_on: [eval-quality]
    config:
      runs_dir: "{output_dir}"
      dataset_path: "labs/design-space.lab/datasets/mas-necessity.yaml"
      metrics:
        - budget_contradiction_detected
        - search_completeness
        - injected_error_detected
```

**Advantages**:

- No extra normalization step (faster)
- Works with standard agent execution
- Suitable for paper reproducibility
- Minimal dependencies

**Limitations**:

- Text-based pattern matching only (no graph-aware ground truth)

---

## Metric implementations

All three metrics are pattern-based (no LLM calls):

1. **budget_contradiction_detected** (mn10)
   - Checks if agent flags $150 total > $120 budget
   - Score: 1.0 (detected), 0.5 (mentions), 0.0 (missed)

2. **search_completeness** (mn11)
   - Counts unique flights mentioned
   - Score: 0.0 (0-1), 0.33 (2), 0.67 (3), 1.0 (4+)

3. **injected_error_detected** (mn12)
   - Checks if agent catches "no direct train Celestia→Luminos"
   - Score: 1.0 (detected), 0.5 (route mention), 0.0 (confirmation bias)

---

## Implementation

```python
provider.compute_from_text(
    final_response=response_text,
    item_id="mn10",
    metric_names=["budget_contradiction_detected"]
)
```

Graph-backed evaluation (normalization extensions) is documented in
Internal knowledge-graph pipeline — not part of OSS.
