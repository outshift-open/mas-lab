<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Conversation summarization and eval models

How mas-lab compresses long conversation history, which LLM it uses, where
the token thresholds come from, and how to override the **summarizer** and
**MCE judge** independently. Default for both is the **same model the agent
uses for turns**.

**Schemas:** `agent.schema.yaml` (`spec.models[]`, `spec.context_manager`,
`spec.working_memory.compaction`) · `experiment.schema.yaml`
(`experiment.evaluation.model`) · **Bindings:** [plugin-bindings.md](plugin-bindings.md)

---

## Why this exists

Long multi-turn agents fill the model context window. Production harnesses
(LangGraph `SummarizationNode` / `ConversationSummaryBufferMemory`, Claude
Code auto-compact, Cursor compact, AutoGen `TokenLimitedChatCompletionContext`,
CrewAI memory summarizer, OpenAI Agents session compaction) all do the same
three things:

1. Keep the **recent** turns verbatim.
2. Compress **older** turns with an LLM (or drop them).
3. Trigger on a **token budget derived from the model context window**, not a
   magic constant.

mas-lab's default `context_manager: summarising` is that pattern. The
summarizer is a **sub-plugin** (`llm` | `drop`) composed by the context
manager — not a second history engine.

---

## How a summary call happens

On every LLM turn, `ContextAssemblerPlugin` builds `messages[]` and asks the
context manager to bound committed history (`manage_history`):

1. Estimate tokens in committed history (`chars ÷ 4` + 4 per message — the
   same heuristic as assembly trim, so we do not depend on a tokenizer).
2. Compare to the **history budget** (below). If under budget, return history
   unchanged.
3. Split into user-turn groups. Keep the last `keep_turns` (default **10**)
   verbatim.
4. Ask the summarizer to compress the prefix:
   - `summarizer: llm` — one out-of-band `engine.summarize_messages` call
     (counts against `spec.budget.max_llm_calls`). The plugin wraps the prefix
     with `params.instructions` or the package default (see [Trigger vs prompt](#trigger-vs-prompt)).
   - `summarizer: drop` — discard the prefix; no LLM call.
5. Cache the summary (**hysteresis**, default `0.2`). New turns append
   verbatim until the managed payload exceeds `budget × 1.2`, so the
   summarizer is not called on every in-turn tool step.

After the turn commits, the same recency cap is written back to
`committed_messages` (folded prefix dropped). See
[context-assembly.md](context-assembly.md).

The summary call is **not** a tracked agent turn. It does not go through the
ReAct loop or tool dispatch.

---

## Trigger vs prompt

**When it fires** is not a user prompt. The CM compares estimated history
tokens to the budget (`context_window − max_tokens`, or
`summary_threshold`). There is no “please summarize now” instruction in the
agent role.

**What the summary LLM sees** is a system prompt plus JSON of older turns.
Default (`SUMMARIZE_INSTRUCTIONS`):

> Summarize the following conversation turns concisely, preserving key facts,
> decisions, and any identifiers (names, IDs, numbers) a later turn might
> need to reference. Write plain prose, not a transcript.

Override with `summarizer.params.instructions`. Empty / omitted → default.

```yaml
params:
  summarizer:
    type: llm
    params:
      model: gpt-4o-mini
      instructions: |
        Preserve city names, dates, and numeric facts. One short paragraph.
```

Runnable pin: [library-standard/examples/context/summarizer-override/](../../library-standard/examples/context/summarizer-override/).

---

## Plugin and CM parameters

`summarizer: llm` constructor params (the only new knobs on that plugin):

| Param | Default | Meaning |
|-------|---------|---------|
| `model` | agent primary model | LiteLLM id or `spec.models[].id` |
| `instructions` | package constant above | System prompt for the summary call |

`drop` has no params. Context-manager knobs (already on `summarising`):

**Default (SOTA, compile-filled):** history budget =
`models[].context_window − models[].max_tokens`.

| Input | Default | Role |
|-------|---------|------|
| `spec.models[].context_window` | `128000` if omitted (`mas-ctl compile` writes it) | Model **input** window |
| `spec.models[].max_tokens` | `2000` | Completion **reserve** — left free so the next answer still fits |
| `summary_threshold` | that difference (`126000` for the defaults) | Trigger for `manage_history` when no assembly budget is passed |
| `trimmer.max_tokens` / `trimmer.reserve_tokens` | `context_window` / `max_tokens` | Assembly-time payload cap (tool-group-aware) |
| `keep_turns` | `10` | Recent user turns never summarized |
| `hysteresis_ratio` | `0.2` | Do not re-summarize until managed history grows 20% past budget |

`summary_threshold: 0` (or omitted before compile) means “derive from the
model window”. An explicit positive `summary_threshold` **wins**. Explicit
`params.trimmer` **wins** over the model-window derivation.

This is **not** tiktoken and **not** the provider's billed usage. It is the
same chars÷4 estimate used for assembly trim, so compaction and trim agree.

`mas-ctl compile agent.yaml` prints the resolved numbers. Trust that output
over remembered defaults.

```yaml
spec:
  models:
    - id: main
      model: gpt-4o
      max_tokens: 2000          # completion reserve
      context_window: 128000    # input window; compile fills if omitted
  context_manager:
    type: summarising           # package default
    params:
      keep_turns: 10
      hysteresis_ratio: 0.2
      summarizer: llm           # agent's primary model
      # summary_threshold: 126000  # compile: context_window − max_tokens
      trimmer:
        max_tokens: 128000
        reserve_tokens: 2000
```

Override the trigger without changing the model:

```yaml
spec:
  context_manager:
    type: summarising
    params:
      summary_threshold: 8000   # compact earlier (absolute estimated tokens)
      trimmer:
        max_tokens: 12000
        reserve_tokens: 512
```

---

## Which model writes the summary?

**Default: the agent's primary model** (`spec.models[]` with `id: main`, or
`models[0]`). The live engine's `model` is bound onto `LlmSummarizer` at
instantiation. Same proxy, same API key; only the `model` field on the
chat-completions payload changes if you override.

### Override on the summarizer sub-plugin (canonical)

`params.model` is a `spec.models[].id` **or** a LiteLLM model string.
Resolution lives in the kernel (`mas.runtime.spec.model_ref`) so
`CMFactory` does not import `library-standard`:

1. empty / omitted → the agent's live engine model (`source=agent`)
2. matching `spec.models[].id` → that entry's `model` string
   (`source=spec.models[id=…]`)
3. same string as the engine model → `source=agent`
4. anything else → sent as a LiteLLM id (`source=override`)

If an id matches a `spec.models[]` row that has no `model` field, fall
back to the agent engine rather than sending the bare id to the provider.

```yaml
spec:
  models:
    - id: main
      model: gpt-4o
      context_window: 128000
      max_tokens: 2000
    - id: summarizer
      model: gpt-4o-mini
      context_window: 128000
      max_tokens: 2000
  context_manager:
    type: summarising
    params:
      summarizer:
        type: llm
        params:
          model: summarizer     # spec.models[].id → gpt-4o-mini
```

Shorthand (top-level `model` on the binding, equivalent):

```yaml
params:
  summarizer:
    type: llm
    model: gpt-4o-mini          # raw LiteLLM id
```

String `summarizer: llm` keeps the agent model. `summarizer: drop` never
calls an LLM.

### Override on `working_memory.compaction` (sugar)

Prefer `spec.context_manager`. If you still use the compaction facade:

```yaml
spec:
  working_memory:
    compaction:
      strategy: summarize
      model: gpt-4o-mini        # → summarizer: {type: llm, params: {model: …}}
      keep_turns: 10
```

If both `context_manager` and `working_memory.compaction` are set,
`context_manager` wins.

### Overlay (per experiment / flavour)

```yaml
apiVersion: mas/v1
kind: Overlay
metadata: {name: cheap-summarizer}
spec:
  target: {kind: Agent}
  patch:
    context_manager:
      type: summarising
      params:
        summarizer:
          type: llm
          params:
            model: gpt-4o-mini
```

---

## Logs (runtime + MCE)

Set log level to **INFO** (`mas-ctl -v` / the lab runner) to see the models.

| Logger | When | What |
|--------|------|------|
| `mas.library.standard.plugins.context.summarizer` | CM bind | `summarizer llm: model=… source=… agent_model=… instructions=default|override` |
| `mas.runtime.engine.llm_live` | each summary HTTP call | `history summarizer: completing N message(s) model=… (override)` |
| `mas.library.standard.plugins.context.conversation` | compaction fires | `compacted N exchange(s) model=… source=… estimated_tokens=… threshold=… keep_turns=…` |
| `mas.library.eval.mce.runner` | MCE jury install | `MCE Jury configured (model=…, source=…, …)` |
| `mas.library.lab.steps.eval.mce` | `eval_mce` step | `judge model=… source=…` |

`source` is the spec field that won (`agent`, `spec.models[id=summarizer]`,
`override`, `experiment.evaluation.model`, `eval_mce.config.model`,
`experiment.metadata.model_name`, `infra`, …).

Compaction also stores `model`, `model_source`, `estimated_tokens`, and
`threshold` on `last_compaction_metadata` (forwarded on the assembler hook as
`_compaction_metadata` for observability). `eval_mce` puts
`judge_model` / `judge_model_source` on the step metadata.

---

## MCE judge model {#mce-judge-model}

`eval_mce` is LLM-as-judge. **Default is the same model as the agent**
(experiment `metadata.model_name`, then workspace infra `default_model`).
Override on the lab spec so every `eval_mce` step inherits it; a per-step
`config.model` still wins.

```yaml
experiment:
  name: topology-ablation
  metadata:
    model_name: gpt-4o          # agent model; also the default judge
  evaluation:
    method: llm_judge
    model: gpt-4o-mini          # cheaper / independent judge
  application:
    post:
      - type: eval_mce          # inherits evaluation.model
        depends_on: [extract_trajectories]
      - type: eval_mce
        name: eval_mce_strict
        config:
          model: gpt-4o         # per-step override
```

Alias: `evaluation.config.model` (the top-level `evaluation.model` wins when
both are set). Interactive labs use the same field on `lab-config.yaml`.

### Resolution order

1. `eval_mce` step `config.model` (or `config.judge_model`)
2. `experiment.evaluation.model`
3. `experiment.evaluation.config.model`
4. pipeline template vars `eval_model` / `judge_model`
5. `experiment.metadata.model_name` / `metadata.model`
6. workspace infra `default_model` (same fallback the agent uses)

Metric *prompts* are owned by MCE (`mce_metrics_plugin`); mas-lab does not
override them. Only the **model id** is a step/lab field.

Runnable pin: [library-eval/examples/mce/judge-override/](../../library-eval/examples/mce/judge-override/).

MCE **metric prompts** are owned by `mce_metrics_plugin`. This repo does not
override them — only the judge **model**.

Runnable pin: [library-eval/examples/mce/judge-override/](../../library-eval/examples/mce/judge-override/).

---

## Compared to other harnesses

| Harness | Trigger | Summarizer model | Recency |
|---------|---------|------------------|---------|
| **mas-lab** | `context_window − max_tokens` (overridable) | Agent model; `summarizer.params.model` override | `keep_turns` (10) + hysteresis 0.2 |
| LangGraph | `max_tokens` on `ConversationSummaryBufferMemory` / `SummarizationNode` | Often a cheaper bound LLM | keep recent messages |
| Claude Code / Cursor | Near the model window | Often a cheaper compact model | keep recent turns |
| AutoGen | `TokenLimitedChatCompletionContext` | Optional transform model | token cap |
| CrewAI | Memory summarizer LLM | Can differ from agent LLM | memory window |
| OpenAI Agents SDK | Session compaction | Session LLM | recent items |

mas-lab follows that shape: window-relative budget, recency pin, optional
cheaper summarizer, judge override on the eval spec.

---

## See also

- [context-assembly.md](context-assembly.md) — assembler, trim, pairing
- [plugin-bindings.md](plugin-bindings.md) — `summarizer` sub-plugin
- [agent.md](agent.md) — `models[]`, `working_memory`
- [experiment.md](experiment.md) — `evaluation.model`
- [Compiled agent defaults](../references/defaults.md) — `mas-ctl compile` expansion
- [working-memory-compaction.md](../design/working-memory-compaction.md) — design history
- [Pipeline steps](https://github.com/outshift-open/mas-lab/blob/main/lab/docs/pipeline-steps.md) — `eval_mce`
- Feature examples (not sample apps): [summarizer-override](../../library-standard/examples/context/summarizer-override/) · [MCE judge-override](../../library-eval/examples/mce/judge-override/)
- Plugin card: [summarizer.md](../../library-standard/src/mas/library/standard/plugins/context/summarizer.md)
