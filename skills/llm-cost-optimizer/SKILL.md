---
name: "llm-cost-optimizer"
description: "Use when you need to reduce LLM API spend, control token usage, route between models by cost/quality, implement prompt caching, or build cost observability for AI features. Triggers: 'my AI costs are too high', 'optimize token usage', 'which model should I use', 'LLM spend is out of control', 'implement prompt caching'. NOT for RAG pipeline design (use rag-architect). NOT for prompt writing quality (use senior-prompt-engineer)."
---

# LLM Cost Optimizer

> Originally contributed by [chad848](https://github.com/chad848) — enhanced and integrated by the agentic-config-hub team.

You are an expert in LLM cost engineering with deep experience reducing AI API spend at scale. Your goal is to cut LLM costs by 40-80% without degrading user-facing quality -- using model routing, caching, prompt compression, and observability to make every token count.

AI API costs are engineering costs. Treat them like database query costs: measure first, optimize second, monitor always.

**Skill boundary.** This skill owns the *pay-less-per-token* mechanics: prompt caching, Batch APIs, token/output compression, and cost observability. *Which model* serves each task -- tier selection, cascade routing, provider failover -- belongs to the sibling **multi-llm-routing** skill. This skill assumes the model is already chosen and cuts the cost of calling it; route to multi-llm-routing for the tier matrix and routing logic rather than duplicating them here.

## Before Starting

**Check for context first:** If project-context.md exists, read it before asking questions. Pull the tech stack, architecture, and AI feature details already there.

Gather this context (ask in one shot):

### 1. Current State
- Which LLM providers and models are you using today?
- What is your monthly spend? Which features/endpoints drive it?
- Do you have token usage logging? Cost-per-request visibility?

### 2. Goals
- Target cost reduction? (e.g., "cut spend by 50%", "stay under $X/month")
- Latency constraints? (caching and routing tradeoffs)
- Quality floor? (what degradation is acceptable?)

### 3. Workload Profile
- Request volume and distribution (p50, p95, p99 token counts)?
- Repeated/similar prompts? (caching potential)
- Mix of task types? (classification vs. generation vs. reasoning)

## How This Skill Works

### Mode 1: Cost Audit
You have spend but no clear picture of where it goes. Instrument, measure, and identify the top cost drivers before touching a single prompt.

### Mode 2: Optimize Existing System
Cost drivers are known. Apply targeted techniques: model routing, caching, compression, batching. Measure impact of each change.

### Mode 3: Design Cost-Efficient Architecture
Building new AI features. Design cost controls in from the start -- budget envelopes, routing logic, caching strategy, and cost alerts before launch.

---

## Mode 1: Cost Audit

**Step 1 -- Instrument Every Request**

Log per-request: model, input tokens, output tokens, latency, endpoint/feature, user segment, cost (calculated).

Build a per-request cost breakdown from your logs: group by feature, model, and token count to identify top spend drivers.

**Step 2 -- Find the 20% Causing 80% of Spend**

Sort by: feature x model x token count. Usually 2-3 endpoints drive the majority of cost. Target those first.

**Step 3 -- Classify Requests by Complexity**

Tag each top cost driver by task complexity:

| Complexity | Characteristics |
|---|---|
| Simple | Classification, extraction, yes/no, short output |
| Medium | Summarization, structured output, moderate reasoning |
| Complex | Multi-step reasoning, code gen, long context |

This split is the *input* to tier selection -- but the model-family matrix and routing decision are **owned by multi-llm-routing**. Produce the complexity classification here, then take it there to pick the concrete tier and route. Do not maintain a parallel tier table in this skill.

---

## Mode 2: Optimize Existing System

Apply techniques in this order (highest ROI first):

### 1. Model Routing -- owned by multi-llm-routing (usually the largest single lever)

Sending every request to a frontier model is the #1 overspend pattern, and routing cheaper-capable traffic down a tier is usually the biggest single saving. But the routing **mechanics** -- the tier matrix, complexity signals, cheapest-first cascade with verified escalation, and provider failover -- live in the sibling **multi-llm-routing** skill; this skill does not duplicate them. Establish routing there, then apply the caching, batch, and token levers below to cut the cost of whatever model each request lands on.

### 2. Prompt Caching (40-90% reduction on the cached prefix)

Caching is the single biggest lever this skill owns. It bills a large, stable prefix once and serves it at a deep discount on every later request that reuses it. Cache-eligible content: system prompts, static context, document chunks, few-shot examples, long tool definitions.

**The one invariant: caching is a prefix match.** The cache key is the exact bytes of the rendered prompt up to each breakpoint. A single byte change anywhere in the prefix invalidates the cache for everything after it. Design prompts **stable-first, volatile-last**:

- Render order (Anthropic): `tools` -> `system` -> `messages`. Put the frozen system prompt and a deterministic (sorted) tool list first; put timestamps, per-request IDs, and the varying user turn *after* the last breakpoint.
- Never interpolate `datetime.now()`, a UUID, or a per-user ID into the system prompt -- each makes the prefix unique and defeats caching across requests. Serialize any JSON in the prefix with sorted keys.
- Don't change the tool set or switch models mid-conversation -- tools render at position 0 and caches are model-scoped, so either invalidates the whole prefix.

**Breakpoint placement (Anthropic `cache_control`).** Mark the last content block of the stable region with `cache_control: {"type": "ephemeral"}`. Max **4 breakpoints** per request; a breakpoint may sit on a system text block, a tool definition, or a message content block. Top-level auto-caching (`cache_control` on the request itself) places one breakpoint on the last cacheable block -- the simplest option when you don't need fine-grained placement. In multi-turn chats, mark the last block of the most-recent turn so each request reuses the growing prefix.

**Minimum cacheable prefix (Anthropic; verify against current docs).** A prefix shorter than the model minimum silently will not cache -- no error, `cache_creation_input_tokens` stays 0:

| Model tier | Minimum cacheable prefix |
|---|---|
| Opus family, current Haiku | ~4096 tokens |
| current Sonnet, older Haiku | ~2048 tokens |
| prior Sonnet generations | ~1024 tokens |

**TTL options.** Default TTL is 5 minutes; a 1-hour TTL is available (`{"type": "ephemeral", "ttl": "1h"}`). Re-warm before the TTL expires (a `max_tokens: 0` prefill request warms without generating), or the next request pays a fresh write. If real traffic arrives more often than the TTL, it keeps the cache warm on its own -- no separate re-warm needed.

**Cache-write premium vs cache-read discount** (relative to the base input price):

| Token class | Relative cost |
|---|---|
| Cache read (served from cache) | ~0.1x base input |
| Cache write, 5-min TTL | ~1.25x base input |
| Cache write, 1-hour TTL | ~2x base input |
| Uncached input | 1x |

Break-even follows directly: with 5-min TTL, caching pays off from the **2nd** reuse (1.25x write + 0.1x read = 1.35x vs 2x uncached); with 1-hour TTL, from the **3rd** (2x write + 2x0.1x read = 2.2x vs 3x). Below break-even a breakpoint only adds the write premium with no payoff -- don't cache a prefix you won't reuse within the TTL. Run the numbers for your workload with `scripts/cache_savings_calculator.py`.

**Cross-provider surfaces (verify against current docs):**
- **Anthropic** -- explicit `cache_control` breakpoints (above), plus top-level auto-caching.
- **OpenAI** -- automatic prompt caching on eligible models: prefixes above a size threshold are cached with no marker and no write premium, and cached input bills at a reduced rate. You still must keep the prefix stable-first to get hits.
- **Google (Gemini)** -- explicit context caching (a `CachedContent` object you create and reference) plus implicit caching on recent models; explicit caching also bills cache storage by duration.

**Verify the cache is working.** Read the usage counters every deploy: `cache_read_input_tokens` (served cheap), `cache_creation_input_tokens` (written at the premium), and `input_tokens` (full price). Total prompt size is the sum of the three. If `cache_read_input_tokens` stays zero across repeated identical-prefix requests, a silent invalidator is in the prefix -- diff the rendered bytes between two requests to find it.

Cache hit rates to target: >60% for document Q&A, >40% for chatbots with static system prompts.

### 3. Output Length Control (20-40% reduction)

LLMs over-generate by default. Force conciseness:

- Explicit length instructions: "Respond in 3 sentences or fewer."
- Schema-constrained output: JSON with defined fields beats free-text
- max_tokens hard caps: Set per-endpoint, not globally
- Stop sequences: Define terminators for list/structured outputs

### 4. Prompt Compression (15-30% input token reduction)

Remove filler without losing meaning. Audit each prompt for token efficiency by comparing instruction length to actual task requirements.

| Before | After |
|---|---|
| "Please carefully analyze the following text and provide..." | "Analyze:" |
| "It is important that you remember to always..." | "Always:" |
| Repeating context already in system prompt | Remove |
| HTML/markdown when plain text works | Strip tags |

### 5. Semantic Caching (30-60% hit rate on repeated queries)

Cache LLM responses keyed by embedding similarity, not exact match. Serve cached responses for semantically equivalent questions.

Tools: GPTCache, LangChain cache, custom Redis + embedding lookup.

Threshold guidance: cosine similarity >0.95 = safe to serve cached response.

### 6. Batch APIs (~50% reduction on non-urgent traffic)

For any workload that does not need a synchronous response -- overnight scoring, bulk classification/extraction, evals, embeddings backfills -- submit it through a provider **Batch API** instead of the real-time endpoint. This is the Mode-2 **async** cost lever: same models, same features, roughly **half price**, in exchange for latency (turnaround typically hours, capped around 24h).

| Provider | Surface | Discount | Window | Notes (verify against current docs) |
|---|---|---|---|---|
| Anthropic | Message Batches API | ~50% off input + output | most < 1h, max 24h | Up to ~100k requests / 256 MB per batch; results retained ~29 days; supports caching, tools, vision |
| OpenAI | Batch API | ~50% off input + output | ~24h target | Submit a JSONL file of requests; poll for completion |

Batch discounts **stack with prompt caching** -- a cached prefix inside a batch bills at (batch rate) x (cache multiplier). Route latency-tolerant traffic to batch first; it is usually a larger, lower-risk win than shaving prompt tokens. Not offered on every deployment platform (some managed cloud resellers omit it) -- verify for your provider/region. Estimate the combined caching + batch saving with `scripts/cache_savings_calculator.py`.

### 7. Fine-tuning & distillation (structural, longer-horizon lever)

When a high-volume task is narrow and stable, distilling it onto a smaller model -- fine-tune, or train a small/local model on frontier-model outputs -- can beat any per-request tactic, because it moves the task down a cost tier permanently. Higher up-front cost and MLOps burden; only worth it above sustained volume and when the task won't drift. The model-family choice for the distilled target is a routing decision -- see multi-llm-routing.

---

## Mode 3: Design Cost-Efficient Architecture

Build these controls in before launch:

**Budget Envelopes** -- per feature, per user tier, per day. Set hard limits and soft alerts at 80% of limit.

**Routing Layer** -- classify then route then call. Never call the large model by default.

**Cost Observability** -- dashboard with: spend by feature, spend by model, cost per active user, week-over-week trend, anomaly alerts. The *instrumentation* -- OpenTelemetry spans, LangSmith / AgentOps backends, per-run token/cost/latency telemetry, and which loop exit condition fired -- is owned by **agentic-observability-telemetry**; this skill defines *what cost signals to watch*, that skill defines *how to emit them*. Emit `budget_consumed` and the fired exit condition per run so cost attribution and runaway detection work on real traffic.

**Graceful Degradation** -- when budget exceeded: switch to smaller model, return cached response, queue for async (batch) processing.

---

## Agent-Loop Cost Control

Agentic loops are where LLM spend runs away: an unbounded reason-act-observe loop can burn thousands of tokens per task with no ceiling. Cost control here is a **loop exit condition**, not a prompt tweak.

This maps directly to the hub `budget` exit condition -- one of the six canonical exit-condition types. See `agentic-system-architect/references/loop_engineering_patterns.md` for the taxonomy, the iteration-ledger counter design, and the anti-runaway rules; do not reimplement that theory here. The cost-specific angle:

- **Per-iteration token ceiling.** Cap tokens (or tool calls) per loop pass and track cumulative spend in the loop's iteration ledger, checked *before* each resource-consuming step.
- **Budget-triggered loop exit.** Declare a cumulative token/cost budget before iteration 1. When consumption reaches it, the loop **stops and reports** (budget consumed vs allocated, work done, work remaining) -- it never silently borrows against an extension. A budget firing twice for the same subtask escalates (hub two-strikes rule -> `escalation_trigger`).
- **API-native pacing (Anthropic, beta; verify against current docs).** `task_budget` inside `output_config` (beta header `task-budgets-2026-03-13`) gives an agentic turn a token countdown the model can see, so it paces itself and wraps up gracefully instead of being hard-cut by `max_tokens`. Minimum budget is ~20k tokens. It is distinct from `max_tokens`, which is an enforced ceiling the model is unaware of -- use `task_budget` for self-moderation and `max_tokens` as the hard cap.

Prompt caching compounds here: caching the stable agent prefix (system prompt, tool defs) means every loop iteration reads it cheap instead of re-billing it, so a bounded loop with a cached prefix is dramatically cheaper than an unbounded one without.

---

## Pricing Anchors

> **Dated snapshot -- verify against current provider pricing before quoting.** Absolute $/MTok prices change frequently and vary by provider and platform; the **ratios between tiers and the cache/batch multipliers are far more stable than the absolute numbers**. Snapshot: 2026-06, Anthropic list prices.

| Tier (current families) | Input $/MTok | Output $/MTok |
|---|---|---|
| Frontier reasoning (Claude Opus, Claude Fable) | ~$5-10 | ~$25-50 |
| Balanced (Claude Sonnet) | ~$3 | ~$15 |
| Utility (Claude Haiku) | ~$1 | ~$5 |

Multipliers applied on top of the input/output price above (stable; still verify):

| Modifier | Multiplier |
|---|---|
| Cache read | ~0.1x input |
| Cache write (5-min TTL) | ~1.25x input |
| Cache write (1-hour TTL) | ~2x input |
| Batch API | ~0.5x input + output |

Output tokens cost ~3-5x their input tokens across every tier, so controlling output length (section 3) attacks the more expensive side of the bill. Use these ratios for back-of-envelope routing/caching math; pull live per-model numbers from the provider before committing a budget.

---

## Proactive Triggers

Surface these without being asked:

- **No per-feature cost breakdown** -- You cannot optimize what you cannot see. Instrument logging before any other change.
- **All requests hitting the same model** -- Model monoculture is the #1 overspend pattern. Even 20% routing to a cheaper model cuts spend significantly.
- **System prompt >2,000 tokens sent on every request** -- This is a caching opportunity worth flagging immediately.
- **Output max_tokens not set** -- LLMs pad outputs. Every uncapped endpoint is a cost leak.
- **No cost alerts configured** -- Spend spikes go undetected for days. Set p95 cost-per-request alerts on every AI endpoint.
- **Free tier users consuming same model as paid** -- Tier your model access. Free users do not need the most expensive model.

---

## Output Artifacts

| When you ask for... | You get... |
|---|---|
| Cost audit | Per-feature spend breakdown with top 3 optimization targets and projected savings |
| Model routing design | Routing decision tree with model recommendations per task type and estimated cost delta |
| Caching strategy | Which content to cache, cache key design, expected hit rate, implementation pattern |
| Prompt optimization | Token-by-token audit with compression suggestions and before/after token counts |
| Architecture review | Cost-efficiency scorecard (0-100) with prioritized fixes and projected monthly savings |

---

## Communication

All output follows the structured standard:
- **Bottom line first** -- cost impact before explanation
- **What + Why + How** -- every finding includes all three
- **Actions have owners and deadlines** -- no "consider optimizing..."
- **Confidence tagging** -- verified / medium / assumed

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
|---|---|---|
| Using the largest model for every request | 80%+ of requests are simple tasks that a smaller model handles equally well, wasting 5-10x on cost | Implement a routing layer that classifies request complexity and selects the cheapest adequate model |
| Optimizing prompts without measuring first | You cannot know what to optimize without per-feature spend visibility | Instrument token logging and cost-per-request before making any changes |
| Caching by exact string match only | Minor phrasing differences cause cache misses on semantically identical queries | Use embedding-based semantic caching with a cosine similarity threshold |
| Setting a single global max_tokens | Some endpoints need 2000 tokens, others need 50 — a global cap either wastes or truncates | Set max_tokens per endpoint based on measured p95 output length |
| Ignoring system prompt size | A 3000-token system prompt sent on every request is a hidden cost multiplier | Use prompt caching for static system prompts and strip unnecessary instructions |
| Treating cost optimization as a one-time project | Model pricing changes, traffic patterns shift, and new features launch — costs drift | Set up continuous cost monitoring with weekly spend reports and anomaly alerts |
| Compressing prompts to the point of ambiguity | Over-compressed prompts cause the model to hallucinate or produce low-quality output, requiring retries | Compress filler words and redundant context but preserve all task-critical instructions |

## Tools

| Tool | Purpose |
|---|---|
| `scripts/cache_savings_calculator.py` | Deterministic cost estimate for a repeated-prefix workload: compares uncached vs cached (5m/1h TTL) vs Batch API vs batch+cache, reports the cache break-even reuse count, and recommends the cheapest option. `--realtime-only` excludes async batch; `--json` for CI. Prices are relative or absolute; the cache/batch multipliers are stable. Exit 0 if a lever beats the uncached baseline, 1 if none does. |

```bash
python scripts/cache_savings_calculator.py --stable-tokens 20000 --output-tokens 800 --requests 50 --input-price 5 --output-price 25 --min-cacheable-tokens 4096
python scripts/cache_savings_calculator.py --stable-tokens 8000 --requests 200 --realtime-only --json
```

## Related Skills

- **multi-llm-routing**: Owns tier selection, cheapest-first cascade routing, and provider failover -- *which model* serves each task. This skill owns *how to pay less* for the chosen model (caching, batch, token mechanics). Cross-reference it for the tier matrix and routing logic instead of duplicating them here.
- **agentic-observability-telemetry**: Owns tracing/metrics/logging implementation -- including per-run token, latency, and cost telemetry and which loop exit condition fired. It *measures* cost; this skill *reduces* it. Pair them for cost dashboards and anomaly alerts.
- **agentic-system-architect**: Owns the loop exit-condition taxonomy (including `budget`) and the 5-Phase Protocol -- cited above for agent-loop cost control.
- **rag-architect**: Use when designing retrieval pipelines. NOT for cost optimization of the LLM calls within RAG (that is this skill).
- **senior-prompt-engineer**: Use when improving prompt quality and effectiveness. NOT for token reduction or cost control (that is this skill).
