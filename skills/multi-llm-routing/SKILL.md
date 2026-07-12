---
name: "multi-llm-routing"
description: "Use when deciding which LLM tier or model family should serve each task or agent node, designing cheap-first cascade routing with verified escalation, binding models per agent/node in CrewAI/LangGraph/MS Agent Framework, or adding provider failover. NOT for prompt caching, batching, or token compression (use llm-cost-optimizer). NOT for eval methodology design (use agentic-evals-benchmarking)."
---

# Multi-LLM Routing

## Overview

Routing is the discipline of sending every task to the **cheapest model that can
verifiably do the job** -- and escalating only on measured failure, never on vibes.
A well-routed system typically serves 60-85% of traffic from the utility tier while
holding a declared quality floor; a badly routed one either overspends (frontier
monoculture) or silently degrades (unverified downgrades).

This skill owns three things:

1. **Tier selection** -- which model *family tier* serves a task, decided by hard
   capability filters first and cost ranking second.
2. **Cascade routing** -- the flagship topology: utility-first, verify, escalate on
   measured failure (FrugalGPT-style), bounded by the hub's six exit conditions.
3. **Per-framework model binding** -- wiring the routing decision into CrewAI,
   LangGraph, and Microsoft Agent Framework nodes/agents.

Caching mechanics, batch APIs, token compression, and spend dashboards belong to the
sibling skill **llm-cost-optimizer**; this skill decides *which model*, that skill
decides *how to pay less for it*.

## Core Capabilities

- Classify tasks into model tiers using deterministic signals before any LLM classifier.
- Design cascade routers with verification predicates that gate escalation.
- Apply capability hard-filters (tool use, structured output, context window) before cost ranking.
- Bind tier decisions to concrete framework APIs (per-agent / per-node model assignment).
- Detect and prevent routing-specific failure modes (ping-pong escalation, silent
  degradation, cache-defeating churn) mapped to the hub exit-condition taxonomy.
- Design provider failover chains for outage and rate-limit resilience.
- Validate routing configs deterministically (`scripts/routing_config_validator.py`).

## Decision Framework 1: Model Tier Matrix

Model names churn quarterly; **tiers and cost ratios are stable**. Route against the
tier, resolve the concrete model ID at deploy time, and re-verify names/prices against
provider docs. Family anchors below are current as of mid-2026 -- treat any hard-coded
model ID in a config as a deploy-time variable, never a design-time constant.

| Tier | Model families (anchors, mid-2026) | Rel. $/MTok in | Rel. $/MTok out | Latency profile | Route here when |
|---|---|---|---|---|---|
| **Frontier reasoning** | Claude Opus family; OpenAI GPT-5-class at high reasoning effort / o-series; Gemini Pro family (thinking); DeepSeek-R1-class open reasoning | 15-60x | 20-75x (*plus* billed reasoning tokens, often 2-10x nominal output) | Seconds to minutes | Architecture, novel multi-step reasoning, root-cause analysis, final synthesis, irreversible-action planning |
| **Balanced** | Claude Sonnet family; GPT-5-class standard effort; Gemini Pro family (non-thinking) | 3-15x | 4-15x | Sub-second start, seconds total | Code completion, structured long-form output, moderate reasoning, agentic tool loops |
| **Utility** | Claude Haiku family; GPT-5-mini/nano class; Gemini Flash / Flash-Lite family | 1x (baseline) | 1x (baseline) | Fastest API tier | Classification, extraction, formatting, JSON validation, summarization, intent detection, routing itself |
| **Local / edge** | Llama, Qwen, Mistral/Ministral, Gemma, Phi families via Ollama/vLLM | No per-token fee (infra + ops only) | -- | Hardware-bound | PII pre-filtering, high-volume categorization, offline/air-gapped, data-residency constraints |

**Calibrated defaults:**

- Reasoning-token billing makes frontier *effective* output cost higher than list
  price. Budget frontier calls at 2-3x their nominal output estimate.
- If a task's expected utility-tier pass rate is >= 60%, cascade (see below) beats
  routing it straight to balanced/frontier on cost -- almost always.
- Local tier only pays off above sustained volume (GPU utilization > ~40%) or under a
  hard data-residency requirement. Below that, utility-tier API calls are cheaper
  than idle GPUs.

## Decision Framework 2: Router Topology

| Topology | Use when | Calibrated default | Cost of the router itself |
|---|---|---|---|
| **Static rules** | < ~5 stable request archetypes; signals are deterministic (length, keywords, endpoint) | Always the first layer, even under other topologies | Zero tokens, microseconds |
| **LLM classifier** | Heterogeneous traffic, > 5 archetypes, rules misroute > ~10% | Classifier runs on utility tier with a <= 200-token prompt | ~1 utility call per request |
| **Cascade** (flagship) | Output quality is cheaply verifiable (schema, tests, rubric); high share of easy tasks | Utility -> balanced -> frontier, `max_escalations = 2` | Wasted attempts on escalated requests |
| **Parallel ensemble** | Answer-critical, budget-insensitive (rare) | k=3 samples + vote, or utility+frontier race | k x cost -- use sparingly |

**Classifier break-even:** a classifier pays for itself when
`downgrade_rate x (cost_frontier - cost_utility) > cost_classifier`. With a
utility-tier classifier (~1x tiny prompt) and a 15x+ frontier/utility gap, break-even
sits below a 5% downgrade rate -- so the classifier nearly always pays off *if* static
rules alone cannot decide. Full math: `references/routing_strategies.md` section 5.

## Decision Framework 3: Routing Signals

Evaluate in this order -- cheap and deterministic first:

| # | Signal | Heuristic | Default threshold / action |
|---|---|---|---|
| 1 | **Capability hard filter** | Does the task need tool calling, native structured output / JSON schema mode, vision, or > N context tokens? | Filter out every tier lacking the capability BEFORE any cost ranking. A cheap model that cannot emit valid tool calls is infinitely expensive. |
| 2 | **Context length** | Prompt + expected retrieval + history tokens | > ~half a tier's context window -> exclude the tier (leave headroom for output and growth) |
| 3 | **Latency SLO** | Interactive (p95 < ~2s to first token) vs batch | Interactive -> exclude thinking/high-effort modes; batch -> cheapest tier passing the quality floor |
| 4 | **Task complexity** | Multi-step verbs (refactor, architect, diagnose, prove), code diffs, ambiguity, cross-document synthesis | 2+ complexity markers -> start cascade at balanced instead of utility |
| 5 | **Structured-output strictness** | Free text vs strict schema consumers downstream | Strict schema -> require native structured-output support + schema-validity predicate |
| 6 | **Blast radius** | Will the output drive an irreversible action? | Irreversible -> frontier tier + HITL gate (see agentic-system-architect); never cascade-downgrade these |

## Cascade Routing (Flagship Pattern)

Run the cheapest capable tier, **verify the output**, escalate one tier only on
measured verification failure. Never escalate on model self-report ("I'm not sure"),
always on a predicate.

```
request -> [hard filters] -> utility attempt -> verify --pass--> serve
                                  |fail
                                  v
                            balanced attempt -> verify --pass--> serve
                                  |fail
                                  v
                            frontier attempt -> verify --pass--> serve
                                  |fail
                                  v
                            escalation_trigger -> human/caller + structured report
```

Expected cost per request: `C = c_u + p_fail_u * (c_b + p_fail_b * c_f)`.
Example with ratios 1 / 6 / 30 and pass rates 70% / 80%:
`C = 1 + 0.3 * (6 + 0.2 * 30) = 4.6x` -- an ~85% saving vs frontier-always (30x),
with every served answer verified.

**Verification predicates** (gate escalation; cheapest first):

1. **Schema validity** -- parse JSON, check required keys/enums/bounds. Deterministic, free.
2. **Deterministic checks** -- unit tests pass, regex/format match, length bounds, citation-present.
3. **Self-consistency** -- k=3 utility samples, majority vote. Costs 3x utility; still far below one frontier call when the ratio exceeds k.
4. **Judge-lite** -- a utility-tier model grades against a 3-5 criterion rubric with a numeric threshold. Cheapest non-deterministic check; calibrate against human labels first (see agentic-evals-benchmarking).

Runnable stdlib implementation, sticky-escalation guard, and quality-floor monitoring:
`references/cascade_routing.md`.

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| Same task bounces utility -> frontier -> utility across turns; spend spikes, answers contradict | **Ping-pong escalation** = `oscillation` (A-B-A-B tier assignment over window 4 for one task signature) | Sticky escalation: once a task signature escalates, pin its tier floor for the session. Detector in `references/cascade_routing.md` section 4. |
| Costs dropped after routing launch, quality complaints rise weeks later | **Silent quality degradation** -- downgrades shipped without a `success_predicate` or quality floor | Per-tier offline eval set before launch; canary-escalation-rate alert (> 1.5x baseline for 1h); weekly regression run. Procedure in `references/cascade_routing.md` section 5. |
| Provider prompt-cache hit rate collapsed after adding the router; net spend UP despite cheaper models | **Cache-defeating router churn** -- alternating models/prefixes destroys prefix-cache reuse; a `budget` failure | Sticky per-session routing; route on conversation start, not per message; monitor cache hit rate per route. Cache mechanics themselves: see llm-cost-optimizer. |
| Requests retry through all tiers repeatedly, no cap fires | **Runaway escalation** -- missing `max_iterations` | `max_escalations = 2` per request; any exit condition firing twice for the same task converts to `escalation_trigger` (hub two-strikes rule). |
| Utility tier emits malformed tool calls / broken JSON in an agent loop, loop spins | **Capability mismatch** -- cost ranking ran before capability filtering | Hard filters first (Decision Framework 3, signal 1). Some cheap models cannot serve agentic nodes at all. |
| 429/5xx storm on one provider takes the whole system down | **No failover chain** | Same-tier cross-provider failover with jittered backoff; degrade tier only after alternates fail. `references/routing_strategies.md` section 4. |
| Identical verification failure at two consecutive tiers | **Task problem, not model-size problem** = `no_progress` | Stop escalating -- a bigger model will not fix a malformed task or an impossible predicate. Return a structured failure report. |

## Hub Canon Integration

A cascade is a loop; it must declare **all six** exit conditions before the first
attempt and passes the same >= 90 HARDENED gate as any agent loop (see
`agentic-system-architect/references/loop_engineering_patterns.md`).

| Hub exit condition | Cascade/router instantiation | Default |
|---|---|---|
| `max_iterations` | `max_escalations` per request | 2 (three tiers max) |
| `no_progress` | Identical verification-failure signature at two consecutive tiers | Stop; do not escalate further |
| `oscillation` | A-B-A-B tier assignment for one task signature over window 4 | Sticky escalation floor per session |
| `budget` | Per-request cost ceiling as a ratio of one frontier single-shot | 3.0x; the cascade must never cost more than a declared multiple of just calling frontier |
| `success_predicate` | The verification predicate, declared before attempt 1, evidence recorded per attempt | Schema validity at minimum |
| `escalation_trigger` | Frontier tier fails verification, or any other condition fires twice | Structured report to human/caller: condition fired, evidence, attempts, recommended next step |

Routing decisions feed Phase 2 (MANIFEST) of the 5-Phase Protocol: the manifest
declares which tier serves each workflow node and why, so the HUMAN GATE reviews
model assignments alongside irreversible actions.

## When NOT to Use

- **Prompt caching, batch APIs, token compression, output-length caps, spend
  dashboards** -> `llm-cost-optimizer` (it owns pay-less-per-call; this skill owns
  which-model).
- **Eval methodology, judge calibration, golden datasets** -> `agentic-evals-benchmarking`
  (this skill only *consumes* eval scores as quality floors).
- **Tracing/metrics implementation** -> `agentic-observability-telemetry`.
- **Framework deep-dives** (graph design, crew design, .NET hosting) ->
  `langgraph-state-design`, `crewai-role-engineering`, `microsoft-agent-framework`;
  this skill covers only the model-binding call sites.
- **Loop guard implementation in Python** -> `loop-engineering-mechanisms`; the
  canonical taxonomy lives in `agentic-system-architect`.
- **RAG-internal model choices** (embedder, reranker) -> `rag-architect`.

## Tools

| Tool | Purpose |
|---|---|
| `scripts/routing_config_validator.py` | Deterministic lint of a routing config JSON: tiers/cascade/exit-condition completeness, cost monotonicity, capability references, failover sanity. `--json` for CI; exit 1 on any ERROR. |

```bash
python scripts/routing_config_validator.py assets/routing-config-example.json
python scripts/routing_config_validator.py my-routing.json --json
```

## References

| File | Summary |
|---|---|
| `references/routing_strategies.md` | Tier matrix rationale, routing signals in depth, per-framework model binding (CrewAI / LangGraph / MS Agent Framework), provider failover, router-overhead economics |
| `references/cascade_routing.md` | Flagship cascade pattern: runnable stdlib skeleton, verification predicates, sticky-escalation oscillation guard, quality-floor monitoring, exit-condition wiring |

| Asset | Summary |
|---|---|
| `assets/routing-config-example.json` | Complete routing config template that passes the validator; copy and adapt |
