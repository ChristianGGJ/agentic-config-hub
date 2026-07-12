# Agent Trajectory Evaluation

Output-only evaluation tells you *whether* an agent succeeded; trajectory evaluation
tells you *how* — and "how" is where agents fail silently: right answer after 40
redundant tool calls, right answer by luck after an oscillation, wrong tool with a
plausible-sounding summary. This reference defines step-level evaluation for tool-using
agents: trajectory match metrics with runnable stdlib implementations, step efficiency,
task-completion scoring, loop-health assertions aligned to the hub's D1-D7 detections,
the public benchmark landscape, and the statistical treatment nondeterministic agents
require.

All code below is Python 3.8+ standard library only — no framework needed. For the
DeepEval/Ragas equivalents (`ToolCorrectnessMetric`, `ToolCallAccuracy`,
`TaskCompletionMetric`, `AgentGoalAccuracy*`), see `deepeval_ragas_api.md`.

---

## 1. The Trace Is the Unit of Evaluation

Evaluate agents on structured traces, not on chat transcripts. The hub's canonical
ReAct trace shape (one entry per think-act-observe cycle) is sufficient for every
metric in this reference:

```json
{
  "agent": "invoice-triage",
  "task": "Resolve ticket #4211",
  "budget": {"max_steps": 20, "max_errors": 3},
  "steps": [
    {
      "n": 1,
      "thought": "Need the ticket body before deciding.",
      "action": {"tool": "get_ticket", "input": {"id": 4211}},
      "observation": "Ticket body: ...",
      "status": "ok"
    }
  ],
  "final_answer": "Refund issued via tool X; confirmation #881."
}
```

Extraction rule for evaluation: the **actual trajectory** is the ordered list of
`(tool, normalized_input)` pairs from `steps[].action`. The **expected trajectory**
is the same shape, authored in your golden dataset. Log observations verbatim —
paraphrased observations make identical calls compare unequal and blind every metric
below.

Normalization (apply to both sides before any comparison):

```python
import json

def normalize_call(tool: str, args: dict) -> tuple:
    """Canonical, hashable signature for one tool call."""
    canon = {str(k).strip().lower(): _norm_val(v) for k, v in (args or {}).items()}
    return (tool.strip().lower(), json.dumps(canon, sort_keys=True))

def _norm_val(v):
    if isinstance(v, str):
        return " ".join(v.split()).lower()   # collapse whitespace, casefold
    if isinstance(v, dict):
        return {str(k).lower(): _norm_val(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_norm_val(x) for x in v]
    return v
```

Failing to normalize is the #1 cause of "tool-call metric reads zero on correct
behavior": `{"id": 4211}` vs `{"id": "4211"}`, key-order differences, trailing
whitespace. Decide explicitly whether numeric/string coercion belongs in `_norm_val`
for your domain.

---

## 2. Tool-Call Correctness Metrics

Four match strictnesses, from brittle to lenient. All are deterministic and free.

```python
from collections import Counter

def exact_match(expected: list, actual: list) -> bool:
    """Same calls, same order, same args. Brittle: any extra step fails."""
    return expected == actual

def in_order_match(expected: list, actual: list) -> bool:
    """Expected calls appear in actual as a subsequence (extras allowed).
    Recommended default for agents with required steps."""
    it = iter(actual)
    return all(e in it for e in expected)   # consumes iterator; preserves order

def any_order_match(expected: list, actual: list) -> bool:
    """Every expected call present (with multiplicity), order ignored."""
    return not (Counter(expected) - Counter(actual))

def precision_recall_f1(expected: list, actual: list) -> dict:
    """Scored variant for dashboards and partial credit."""
    exp, act = Counter(expected), Counter(actual)
    tp = sum((exp & act).values())
    precision = tp / max(sum(act.values()), 1)
    recall = tp / max(sum(exp.values()), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {"precision": round(precision, 4),
            "recall": round(recall, 4), "f1": round(f1, 4)}
```

Usage: build both lists with `normalize_call` and pick strictness per the decision
table in SKILL.md. Two-level scoring is often best: **name-level** recall (did it call
the right tools at all?) gated at 1.0, plus **args-level** F1 (were the arguments
right?) gated at >= 0.9. Compute name-level by passing `(tool, "")` signatures.

**Argument accuracy** (per matched call, when you need finer grain than pair
matching): fraction of expected argument keys whose normalized values match. Report
per-tool so a single chatty tool cannot hide a broken one.

---

## 3. Step Efficiency

Correct-but-wasteful trajectories regress cost and latency long before they regress
accuracy. Record these per eval case:

```python
def step_metrics(actual: list, optimal_steps: int) -> dict:
    """actual: normalized (tool, args) list; optimal_steps: authored in the golden."""
    n = len(actual)
    dupes = n - len(set(actual))
    return {
        "steps": n,
        "efficiency": round(optimal_steps / max(n, 1), 4),  # 1.0 = optimal
        "redundancy_rate": round(dupes / max(n, 1), 4),     # repeated identical calls
    }
```

- `optimal_steps` is a label in your golden dataset: the step count of a competent
  reference trajectory (author it when you author `expected_calls`).
- Calibrated gates: `efficiency >= 0.5` (agent may take up to 2x the reference
  path), `redundancy_rate <= 0.2`. Tighten with maturity.
- Also track **backtrack count** (calls whose effect is undone by a later call, e.g.
  write-then-revert) if your tools expose inverses; rising backtracks predict
  oscillation.

---

## 4. Task-Completion Scoring

Score completion in two tiers; never skip tier 1.

**Tier 1 — deterministic success predicate (always prefer).** The hub's
`success_predicate` exit condition *is* the completion metric: an evidence-producing,
machine-checkable test. Examples: target file exists and parses; `pytest -q` exits 0;
the API returns the created resource; the final JSON validates against a schema. Score
is binary per run; aggregate as pass rate or pass@k (section 7). If you cannot write
the predicate, the task is not ready for autonomous execution — or for evaluation.

**Tier 2 — LLM-judged completion (fuzzy goals only).** For goals like "summarize and
propose next actions", use a rubric-anchored judge (design rules in
`eval_methodologies.md`) or a framework metric (`TaskCompletionMetric` in DeepEval,
`AgentGoalAccuracyWithReference` in Ragas — see `deepeval_ragas_api.md`). Judge the
*outcome against the stated goal*, and give the judge the trace's `final_answer` plus
the tool observations as evidence — judging the answer alone rewards confident
fabrication.

**Hybrid pattern (recommended for most agents):** predicate for the hard shell
(artifact exists, schema valid, no forbidden actions in trace), judge for the soft
interior (quality of the content). Gate on the predicate; trend the judge score.

---

## 5. Loop-Health Assertions (Hub D1-D7 as Eval Checks)

The hub's canonical trace detections are free trajectory assertions. Run them over
every eval trace and treat the health score as a regression metric alongside
accuracy. Severity weights and verdict bands mirror hub canon: start at 100,
subtract 30 per CRITICAL, 15 per HIGH, 5 per MEDIUM; **>= 90 = HEALTHY** (gate),
60-89 DEGRADED, < 60 RUNAWAY.

| ID | Assertion over the trace | Severity | Eval meaning |
|----|--------------------------|----------|--------------|
| D1 | No identical `(tool, input)` appears >= 3 times | CRITICAL | Action loop: agent retries the same call hoping for new results |
| D2 | No A-B-A-B alternation in any window of 4 actions | HIGH | Oscillation: two steps undo each other |
| D3 | Consecutive `status == "error"` < `budget.max_errors` (default 3) | HIGH | Error cascade instead of diagnosis |
| D4 | Every step has non-empty `thought` and `observation` | MEDIUM | ReAct contract violation; step template not enforced |
| D5 | `len(steps)` < `budget.max_steps` | CRITICAL | Budget overrun; loop guard missing or unchecked |
| D6 | `final_answer` present when last status is `ok` | MEDIUM | No convergence: agent stopped without concluding |
| D7 | No identical `thought` text >= 3 times | MEDIUM | Reasoning loop; re-deriving the same conclusion |

Minimal stdlib checker for the two CRITICAL detections (extend per the table):

```python
from collections import Counter

def critical_detections(trace: dict) -> list:
    findings = []
    calls = [normalize_call(s["action"]["tool"], s["action"].get("input", {}))
             for s in trace["steps"] if s.get("action")]
    repeats = [c for c, n in Counter(calls).items() if n >= 3]
    if repeats:
        findings.append({"id": "D1", "severity": "CRITICAL", "evidence": repeats})
    if len(trace["steps"]) >= trace.get("budget", {}).get("max_steps", 20):
        findings.append({"id": "D5", "severity": "CRITICAL",
                         "evidence": len(trace["steps"])})
    return findings
```

CI rule of thumb: **zero CRITICAL detections on any golden trace, suite-median health
>= 90.** This is the dynamic complement to the flagship's static config gate (loop
audit >= 90 = HARDENED): the config gate proves the agent is designed safely; these
assertions prove each evaluated run behaved safely. Additionally, record **which of
the six exit-condition types ended each run** (`success_predicate`, `max_iterations`,
`no_progress`, `oscillation`, `budget`, `escalation_trigger`); any should-pass golden
that exits via anything other than `success_predicate` is a failure even if the final
answer happens to be right.

---

## 6. Public Agent Benchmark Landscape

Use public benchmarks to compare *models and harnesses*, never as a substitute for a
domain golden set — leaderboard rank does not transfer to your tools and your data.
Landscape as of 2025/2026 (verify current leaderboard/versions before citing numbers):

| Benchmark | What it measures | Use it when | Caveats |
|---|---|---|---|
| SWE-bench (prefer the Verified subset) | Resolving real GitHub issues: patch generation validated by the repo's tests | Choosing a model/harness for coding agents | Contamination risk on older issues; harness quality dominates scores |
| GAIA | General assistant tasks requiring tool use, browsing, multi-step reasoning, with unambiguous answers | Testing general tool-using assistants | Answer-matching only; no trajectory credit |
| tau-bench (τ-bench) | Multi-turn user-simulation in retail/airline domains with policy compliance; pass^k for reliability | Customer-facing agents that must follow policies across turns | Simulated users; two domains only |
| AgentBench | Broad multi-environment suite (OS, DB, web, games) | Wide comparative screening of models as agents | Breadth over depth; environments age |
| WebArena | Long-horizon tasks on self-hosted realistic websites | Browser/web agents | Hard setup; success detection is task-specific |

Selection rule: pick the one benchmark closest to your domain as an external anchor,
then invest the rest of the effort in your own golden set — 100 domain cases beat any
leaderboard delta for predicting your production behavior.

---

## 7. Statistical Rigor for Nondeterministic Agents

Single-run scores are noise. Treat every reported number as a sample statistic.

**pass@k** — probability that at least one of k sampled runs succeeds. Compute with
the unbiased estimator over n >= k runs with c successes:

```python
from math import comb

def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k given n total runs and c successful runs."""
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)
```

- **Gate on pass@1** (reliability users experience); **report pass@k** (capability
  ceiling). An agent with pass@1 = 0.6 and pass@5 = 0.95 has a consistency problem,
  not a capability problem — fix determinism (temperature, tool flakiness, prompt
  ambiguity) before fixing capability.
- tau-bench's pass^k (all k runs succeed) is the stricter reliability variant; use it
  when the agent must be right every time.

**Run-to-run variance procedure:** run the full suite k >= 5 times on the unchanged
baseline; record per-metric mean and stddev; the **noise band is +/- 2 stddev**. A
candidate change is a regression/improvement only if its mean falls outside the band.
Gate CI on the *lower* bound of the candidate's runs (pessimistic), not the best run.

**Minimum sample size:** with fewer than ~30 cases, one flipped case moves pass rate
by > 3 points — below the noise you are trying to detect. Floors: 30 to gate at all,
100-300 for stable means, 10+ per reported slice. Wilson or bootstrap intervals are
overkill for most teams; the k-run noise band is the 80/20.

---

## 8. Cost & Latency Guardrail Metrics

Record per eval case, alongside quality scores — these map to the hub's `budget`
exit-condition type and catch regressions quality metrics miss:

- `input_tokens`, `output_tokens` (sum across all steps, including judge calls if you
  bill them to the run)
- `tool_calls` (equals `len(steps)` in the canonical trace)
- `wall_time_s`, and per-tool latency if any tool is rate-limited
- `exit_condition` (which of the six types ended the run)

Gates: p95 tool calls <= `budget.max_steps`, p95 tokens within 1.5x of the baseline
median, and zero runs exiting via `budget` on should-pass goldens. Feed the same
fields into `scripts/eval_gate.py` as ordinary metrics (e.g.
`{"metric": "p95_tool_calls_ok", "score": 1.0}` computed by your runner). Production
telemetry for these signals is owned by the agentic-observability-telemetry sibling;
this skill consumes its traces offline as eval inputs.
