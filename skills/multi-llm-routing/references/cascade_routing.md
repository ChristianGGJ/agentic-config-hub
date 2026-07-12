# Cascade Routing

Cascade routing runs the **cheapest capable model first**, verifies its output, and
escalates to a stronger tier only on measured failure. It is the highest-ROI routing
topology because most requests are handled at the utility tier and only genuinely hard
ones pay frontier prices. (FrugalGPT-style cascade.)

> Ownership: this file owns cascade *routing* logic. Token/caching cost mechanics live
> in `llm-cost-optimizer`; theory of loop bounding lives in the flagship
> `agentic-system-architect/references/loop_engineering_patterns.md`.

## 1. The cascade loop

```
request
  -> tier_0 (utility model)         # cheap, fast, local/small
       -> verify(output)            # cheap predicates, see section 3
            PASS -> return
            FAIL -> tier_1 (mid)
                 -> verify(output)
                      PASS -> return
                      FAIL -> tier_2 (frontier / reasoning)
                           -> return (or escalate to human)
```

Rules:
- **Escalate on evidence, not anticipation.** A request goes up a tier only when a
  verification predicate on the lower tier's output fails — never pre-emptively by
  guessing difficulty.
- **Cap the ladder.** The number of tiers is a hard `max_iterations` bound. A 3-rung
  cascade escalates at most twice; the top rung returns its answer or hands off to a human.
- **Account the spend.** Each escalation adds the lower tier's (now wasted) cost. A
  cascade only saves money when the lower tiers resolve the majority of traffic; measure
  the escalation rate and pull the tier floor up if it exceeds your break-even point.

## 2. Break-even math

Let `p` = fraction resolved at the utility tier, `c_u` = utility cost, `c_f` = frontier
cost. Cascade expected cost per request is approximately `c_u + (1 - p) * c_f`
(you always pay the utility rung, then the frontier rung on the misses). Cascade beats
"frontier-only" (`c_f`) whenever `c_u + (1 - p) * c_f < c_f`, i.e. `p > c_u / c_f`.
With a utility tier ~1/20th the cost of frontier, you need only ~5% of traffic resolved
cheaply to break even — but the *quality* of verification decides `p`, so invest there.

## 3. Verification predicates that gate escalation

Escalation quality is only as good as the verifier. Order from cheapest to most costly;
stop at the first that fails.

| Predicate | Cost | Catches |
|-----------|------|---------|
| Schema / format validity (JSON parses, required fields present) | ~free | Malformed structured output |
| Constraint checks (length, enum membership, numeric range) | ~free | Out-of-contract answers |
| Self-consistency (sample twice at low temp, compare) | 2x utility | Unstable / low-confidence answers |
| Groundedness check (answer cites provided context) | 1 cheap call | Hallucination on RAG tasks |
| Judge-lite (small model scores the answer against a rubric) | 1 utility call | Subtle quality failures |

Keep verification cost well below the escalation it prevents; a verifier that costs as
much as the frontier call defeats the cascade.

## 4. Sticky escalation — the oscillation guard

Without memory, a task can bounce utility -> frontier -> utility across turns as its
phrasing drifts, spiking cost and contradicting itself. This is the `oscillation` exit
condition (A-B-A-B tier assignment over a window of 4 for one task signature).

**Detector (stdlib pattern):**

```python
from collections import deque

class TierFloor:
    """Pin a task signature's minimum tier once it has escalated, for the session."""
    def __init__(self, window=4):
        self.floor = {}                      # signature -> min tier index
        self.history = {}                    # signature -> deque of recent tiers

    def decide(self, signature, proposed_tier):
        tier = max(proposed_tier, self.floor.get(signature, 0))
        h = self.history.setdefault(signature, deque(maxlen=4))
        h.append(tier)
        # A-B-A-B oscillation over window 4 -> pin the floor up
        if len(h) == 4 and h[0] == h[2] and h[1] == h[3] and h[0] != h[1]:
            self.floor[signature] = max(h)   # never drop below the higher tier again
        return tier
```

Once a signature escalates, pin its tier floor for the rest of the session so it cannot
oscillate back down. Reset floors between sessions (they are cost heuristics, not
correctness state).

## 5. Hub canon integration

| Exit condition | Cascade meaning |
|----------------|-----------------|
| `max_iterations` | Number of cascade rungs (hard cap on escalations) |
| `budget` | Cumulative spend across rungs; abort/return-best when exhausted |
| `oscillation` | A-B-A-B tier reassignment for one signature (section 4) -> pin tier floor |
| `no_progress` | Two consecutive rungs return equivalent failing output -> stop escalating, hand off |
| `success_predicate` | A verification predicate (section 3) passes |
| `escalation_trigger` | Top rung still fails, or a high-stakes task -> route to human |

Declare all six before the first request, per the flagship loop-engineering rules.

## 6. Failure modes

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Cost higher than frontier-only | Escalation rate above break-even (`p` too low) | Raise the utility tier's capability, or the tier floor; improve verifier recall |
| Ping-pong tier assignment, contradictory answers | `oscillation` — no sticky floor | Pin tier floor per signature (section 4) |
| Good answers rejected, everything escalates | Verifier too strict (low precision) | Loosen predicates; measure verifier FP rate |
| Bad answers pass at utility tier | Verifier too weak (low recall) | Add a groundedness or judge-lite predicate |
| Latency worse than expected | Serial verification on every request | Run cheap predicates inline, defer judge-lite to async spot checks |
