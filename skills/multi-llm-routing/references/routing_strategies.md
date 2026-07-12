# Multi-LLM Routing Strategies

Depth reference for the multi-llm-routing skill. Covers the tier matrix rationale,
routing signals, per-framework model binding, provider failover, and router-overhead
economics. Section numbers are stable citation targets from `SKILL.md`.

> Assumes current-generation model families (2025/2026). **Never hard-code model IDs**
> in routing code — read them from config by tier (see section 3), because model names
> and prices churn quarterly. Token/caching cost mechanics belong to the sibling
> `llm-cost-optimizer` skill; this file owns tier *selection* and *binding*, not caching.

## 1. Tier matrix rationale

Route by the cheapest tier that clears the task's quality bar, not by habit.

| Tier | Role | Relative cost | Use for |
|------|------|---------------|---------|
| Utility | small/fast general model | ~1x | Extraction, classification, routing decisions, short chat |
| Mid | mid-size general model | ~5-8x | Summarization, code, most tool-use turns |
| Reasoning / frontier | top reasoning model | ~15-25x | Multi-step planning, hard reasoning, final synthesis |
| Local / edge | self-hosted small model | ~0 marginal | High-volume, latency/privacy-sensitive, offline |

The ratios, not the absolute prices, drive routing math (section 5). Keep the matrix in
config so a model swap is a config edit, not a code change.

## 2. Routing signals

Decide the tier from observable request features, cheapest signal first:

| Signal | Cheap to compute? | Pushes toward higher tier when |
|--------|-------------------|-------------------------------|
| Task type (from the caller/intent) | yes | planning / multi-step reasoning |
| Input length / context size | yes | long context needing synthesis |
| Structured-output requirement | yes | strict schema + high stakes |
| Historical failure rate for this task class | yes (from telemetry) | class often fails at utility tier |
| Explicit difficulty hint / user tier | yes | premium SLA or flagged-hard task |
| Classifier score (a small model rates difficulty) | no (1 utility call) | classifier says "hard" past break-even (section 5) |

Prefer rule-based signals; only add a classifier call when rules alone misroute often
enough to pay for it (section 5).

## 3. Per-framework model binding

The routing decision is abstract; each framework binds it differently. Read tiers from
config and inject the chosen model at construction — the router returns a *tier name*,
the binding layer maps that name to a concrete client. No framework sees a hard-coded ID.

**LangGraph** (as of LangGraph 1.x; verify against current docs) — a router node emits
the tier into state; downstream nodes construct their model from the resolved tier:

```python
# TIERS loaded from config: {"utility": {"model": ..., "provider": ...}, "reasoning": {...}}
from langchain.chat_models import init_chat_model            # provider-agnostic factory

def make_model(tier_cfg):
    return init_chat_model(tier_cfg["model"], model_provider=tier_cfg["provider"])

def solve_node(state):
    model = make_model(TIERS[state["tier"]])                 # tier chosen upstream by a router node
    return {"answer": model.invoke(state["messages"])}
```

**CrewAI** (verify against current docs) — set `llm` per Agent from the resolved tier; a
planner agent may run reasoning-tier while workers run utility-tier:

```python
from crewai import Agent, LLM
def agent_for(tier_cfg, **kw):
    return Agent(llm=LLM(model=tier_cfg["model"]), max_iter=kw.pop("max_iter", 5), **kw)
```

**Microsoft Agent Framework** (C#; verify against current docs) — build the
`ChatClientAgent` from an `IChatClient` selected by tier; keyed DI registers one client
per tier and the router resolves the key:

```csharp
// services.AddKeyedChatClient("utility", ...); AddKeyedChatClient("reasoning", ...);
var client = sp.GetRequiredKeyedService<IChatClient>(tier);  // tier chosen by the router
var agent  = new ChatClientAgent(client, instructions);
```

## 4. Provider failover

Availability routing is orthogonal to cost routing: a tier can have multiple providers.

- **Same-tier cross-provider failover.** On 429/5xx/timeout, retry the *same tier* on an
  alternate provider before ever downgrading the tier — a rate limit is not a reason to
  lose capability.
- **Jittered exponential backoff**, with total attempts capped as a `max_iterations`
  bound so failover cannot loop forever.
- **Degrade tier only after alternates fail.** If every provider at the tier is down and
  the task allows it, drop one tier with a logged quality caveat; otherwise fire
  `escalation_trigger`.
- **Circuit-breaker per provider.** After N consecutive failures, open the breaker and
  skip that provider for a cooldown so you stop paying latency on a dead endpoint.

```
call(tier):
  for provider in tier.providers_in_priority_order():
     if breaker_open(provider): continue
     try: return provider.invoke(...)
     except (RateLimit, ServerError, Timeout): backoff_jittered(); record_failure(provider)
  if task.allows_degrade and tier.lower_exists(): return call(tier.lower())
  raise Escalate("all providers exhausted at tier %s" % tier)   # escalation_trigger
```

## 5. Router-overhead economics (classifier break-even)

Adding a classifier call to route better only pays when its cost is less than the
misrouting it prevents. Let `c_clf` = classifier cost, `c_u` = utility cost,
`c_f` = frontier cost; rule-based routing misroutes fraction `m`, a classifier cuts it
to `m'`. The classifier is worth it per request when:

```
c_clf < (m - m') * (c_f - c_u)
```

The classifier's fixed cost must be smaller than the expected misrouting cost it removes.
With a utility-priced classifier and a large `c_f - c_u` gap, a few points of misrouting
reduction pays. If rules already route well (`m` small), skip the classifier — its fixed
cost dominates. Measure `m` from telemetry before adding a classifier and re-measure
after; one that does not move `m` is pure overhead.

## 6. Hub canon integration

| Exit condition | Routing meaning |
|----------------|-----------------|
| `max_iterations` | Cap on failover attempts and cascade rungs (see `cascade_routing.md`) |
| `budget` | Cumulative spend across tiers/retries; halt when exhausted |
| `oscillation` | A-B-A-B tier reassignment for one task signature -> pin tier floor |
| `no_progress` | Repeated equivalent failures across providers/tiers -> stop, escalate |
| `success_predicate` | A verification predicate passes at the chosen tier |
| `escalation_trigger` | All providers/tiers exhausted, or a quality floor breached |

Cascade routing (cheapest-first-then-escalate) is the companion topology — see
`references/cascade_routing.md`.
