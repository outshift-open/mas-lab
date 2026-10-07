<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Context Management

This reference describes what a model request contains, what is pinned or
summarized, how MAS Lab derives context budgets, and how to inspect token and
cache usage while debugging. The manifest-level controls remain documented in
[context assembly](../manifests/context-assembly.md) and
[conversation summarization](../manifests/summarization.md).

## Request Composition

The engine sends an OpenAI-compatible chat request. Its message sequence is
assembled in this order:

1. A system message containing the agent context, memory seeds, and collected
   `ContextPart` sections. Context sections are ordered by placement and then
   priority.
2. Managed committed history: an optional summary followed by recent turns.
3. The current user turn.
4. In-turn working memory, including the live tool-call/result group.

Function tool schemas are sent separately in the request's `tools` field, not
inside `messages[]`. They are rebuilt for each model call and count toward the
model's context window. They are not conversation history and are never
summarized.

## Pinned and Summarized State

The system message is reconstructed for every model call, outside committed
conversation history. History summarization therefore does not rewrite the
agent's role prompt or collected system context.

`ContextPart.pinned` controls whether a context-budget strategy may evict a
section. `ContextPart.skills()` pins the skill catalog by default. The native
skills plugin also pins the full body of each activated skill as a
`skills/activated/<name>` system part by default. These parts are re-injected on
every call and are not passed to the conversation summarizer. The activation
tool result also remains in history; that duplicate history copy may later be
summarized, while the pinned system copy remains until the skill is unloaded or
the session ends.

Committed conversation history is the summarizer's input. The summarizing
context manager keeps the latest `keep_turns` user turns verbatim and compresses
older turns. Tool-call and tool-result groups are kept together. The live
working-memory tail is separately pinned during assembly, but the trimmer may
drop its oldest complete tool groups if the fixed context leaves insufficient
room.

`inspect_context` returns only numeric usage, cache results, and metadata such
as source, section, and pinned status. It does not return prompt text or tool
arguments. Existing full-content observability traces may still contain messages
when content tracing is enabled; treat those traces as sensitive.

## Model Window Resolution

An omitted `spec.models[].context_window` means **auto**. Resolution order is:

1. Explicit agent model `context_window` override.
2. Infra `generation.context_window` override.
3. The model catalog entry for the model actually resolved after infra model
   mappings.
4. The default fallback, 128,000 tokens, with a warning naming the unresolved
   model and the override field to use.

The built-in catalog records Gemini 2.5 Flash at 1,048,576 input tokens. A
compiled generic value is not written back as an explicit 128,000-token model
override: infra may remap `any` or an experiment model after compile. The
runtime therefore resolves the final window when the live engine is built.

MAS Lab does not make a network request to LiteLLM or another provider to
look up context metadata at startup. Known models use the local catalog; custom
or proxy-only model names should specify `context_window` on the model binding
or `generation.context_window` in infra. This keeps startup deterministic and
avoids an additional credentialed network dependency.

The completion reserve comes from the effective output-token budget, then the
model binding, then the documented 2,000-token fallback. A user can override
`max_tokens`, `context_window`, and the trimmer settings independently.

## Safety Margin and Hysteresis

The automatic budget accounts for the resolved window, completion reserve,
fixed system/context content, current input, working memory, and tool schemas.
It keeps a configurable safety margin for tokenizer approximation and provider
request overhead. The default `trimmer.safety_margin_ratio` is `0.1` (10% of the
resolved input window).

For automatic summarization, the soft trigger is lower than the hard
safety-bounded history limit by `1 + hysteresis_ratio`. With the default
`hysteresis_ratio: 0.1`, the summarizer has room to reuse the cached summary as
new turns accumulate, while its retrigger ceiling stays inside the hard budget.
The defaults are intentionally coordinated: margin protects the provider
boundary; hysteresis avoids changing the prompt on every turn and helps retain
LLM cache hits.

A positive `summary_threshold` sets an earlier absolute estimated-history
trigger. It is capped by the resolved safety-bounded budget. `trimmer.max_tokens`,
`trimmer.reserve_tokens`, and `trimmer.safety_margin_ratio` override the
corresponding assembly limits. Setting the margin to zero is possible but not
recommended with an estimated counter.

```yaml
spec:
  models:
    - id: main
      model: any
      max_tokens: 12000
      # context_window omitted: resolve from the runtime model
  context_manager:
    type: summarising
    params:
      keep_turns: 10
      hysteresis_ratio: 0.1
      trimmer:
        reserve_tokens: 12000
        safety_margin_ratio: 0.1
```

For a deployment whose provider has an authoritative window different from the
catalog:

```yaml
# LLMProxy or LLMLocal infra
spec:
  generation:
    context_window: 200000
```

  An infra owner can also override the catalog's per-million-token pricing for a
  proxy or negotiated deployment rate:

  ```yaml
  spec:
    generation:
      pricing:
        input_per_million_tokens: 0.30
        cached_input_per_million_tokens: 0.03
        output_per_million_tokens: 2.50
  ```

The full request is estimated with a conservative `characters / 4` heuristic
plus message/tool overhead. Provider-reported `prompt_tokens` is recorded after
the call and is the better measurement for calibration. The estimate includes
tool schemas and text messages, but is not a provider tokenizer; multimodal
payloads and model-specific tokenization can still differ. The final trim keeps
complete tool-call/result groups intact. If pinned context alone exceeds the
budget, it is retained and a warning is emitted rather than silently deleting
instructions.

## Inspecting Context Usage

Every assembled LLM call records a `context.assembled` event with an estimated
request total, token breakdown, context window, completion reserve, remaining
budget, and metadata-only context parts (`source`, `section_id`, `placement`,
`tokens`, `pinned`). The latest snapshot is also available through the control
contract and JSON-lines RPC:

```text
inspect_context(session_id)
```

The returned `ContextUsageView` includes:

- The latest request's resolved model/window, estimated prompt tokens, reserve,
  remaining budget, fill ratio, and token breakdown.
- Metadata for pinned and non-pinned context parts, without their text.
- The most recent provider usage report, when available, with
  `provider_usage_source` set to `provider`, `cached_response`, or `unavailable`.
- Request-level cache hit/miss counts and rate, plus raw probe counts by cache
  layer. A request passing through nested caches is counted once in the overall
  rate and once per probed layer in the layer breakdown.
- The cumulative estimated provider cost for this session, and
  `cost_status`. Response-cache hits add zero provider cost.

Inspection is read-only: it does not reassemble the prompt, call the model, or
change cache keys. The snapshot is the latest assembled request; before the
first model call it is unavailable.

## Tokens, Cache, and Cost

MAS Lab records provider usage fields such as `prompt_tokens`,
`completion_tokens`, and provider-specific cached-token details when the
provider returns them. A response-cache hit is recorded separately, by cache
layer (`infra_llm_cache` or `provider_cache`). A strict infra cache miss is a
`cache.lookup` event, not a fabricated model completion. The hit rate is
computed per cache layer from observed lookups; write-only recording has no
lookup denominator.

A cached response may carry the usage from the original live request. It is
useful for context analysis but is **not** new billable usage. Provider prompt
caching is different: the request still reaches the provider, and cached input
tokens are represented in provider usage if supported.

The model catalog can store versioned pricing rates, and infra
`generation.pricing` can override them. As of 2026-10-06, the catalog records
Vertex AI Gemini 2.5 Flash text rates from the
[Vertex AI pricing page](https://cloud.google.com/vertex-ai/generative-ai/pricing):
$0.30/M uncached input, $0.03/M cached input, and $2.50/M output. This is an
estimate: a LiteLLM proxy may use another region, account discount, or markup;
set the infra override to model that deployment. Models without known rates
remain unpriced (`cost_status: pricing_or_usage_unavailable`).

For live provider calls, estimated cost uses:

```text
uncached_input_tokens × input_rate
+ cached_input_tokens × cached_input_rate
+ output_tokens × output_rate
```

Response-cache hits have zero upstream model-call cost; provider prompt-cache
hits use the configured cached-input rate. Cost is cumulative over recorded
`LLM_CALL` returns for the session, not a billing invoice. Exact invoices may
differ due to region, tier, discounts, retries, multimodal tokens, and proxy
billing policy.

## Cache Stability

The response cache key depends on the exact prompt, tool definitions, and model
parameters. Context ordering and tool ordering are therefore behavioral: do not
add timestamps, random identifiers, or unstable ordering to prompt content.
The context snapshot is telemetry only and does not enter the request or cache
key. Hysteresis, stable system/context parts, and unchanged tool schemas keep
requests identical between compaction points.

## Framework Practice

MAS Lab uses local assembly because the demo runs through OpenAI-compatible Chat
Completions, including Gemini via LiteLLM. The OpenAI Responses API's server-side
compaction item is not available on this route.

- [LangGraph short-term memory](https://docs.langchain.com/oss/python/langgraph/add-memory#manage-short-term-memory)
  documents token-aware trim/summarize steps and preserving valid tool-message
  groups.
- [Anthropic context windows](https://platform.claude.com/docs/en/docs/build-with-claude/context-windows)
  count system prompts, messages, tool results, tool definitions, and output;
  the provider also offers token counting, context editing, and compaction.
- [OpenAI compaction](https://developers.openai.com/api/docs/guides/compaction)
  compacts at a configured threshold and returns a continuation item for the
  Responses API.

The practical pattern is consistent: measure the whole request, reserve output
space, compact before the hard provider limit, preserve recent/tool-boundary
state, and expose the exact budget decision to debugging tools.
