# Agent-Loop Telemetry (Hub Canon)

Generic tracing captures model calls and tool calls. It does not capture the *control
loop* — how many iterations ran, how deep delegation went, whether the agent oscillated,
and which exit condition ended the run. This reference defines those signals as
first-class telemetry so a dashboard can answer "why did this agent stop?" without a log
dive.

> Vocabulary source: the six exit-condition types are defined in
> `agentic-system-architect/references/loop_engineering_patterns.md`. This file is the
> *telemetry* projection of that taxonomy; it does not redefine it.

## 1. Span attributes on the agent-loop span

Open one span per agent run (the loop), child spans per iteration. On the loop span set:

| Attribute | Type | Notes |
|-----------|------|-------|
| `agent.name` | string | Which agent/role |
| `agent.run_id` | string | Correlation id shared with logs |
| `agent.iterations` | int | Total iterations executed |
| `agent.max_iterations` | int | The declared cap (so % consumed is derivable) |
| `agent.delegation_depth` | int | Max sub-agent nesting reached |
| `agent.oscillation_count` | int | A-B-A-B action/state repetitions detected |
| `agent.budget_consumed` | number | Tool calls / tokens / seconds used |
| `agent.budget_limit` | number | Declared budget (same unit) |
| `agent.exit_condition` | enum | One of the six canon values (section 2) |
| `agent.exit_detail` | string | Human-readable reason |

## 2. The exit-condition dimension

`agent.exit_condition` is a **closed enum** — charting it across runs shows the health
of a fleet at a glance (a spike in `no_progress` or `oscillation` is a design smell).

```
max_iterations     | hit the iteration cap without success
no_progress        | N iterations with no state change
oscillation        | A-B-A-B action/state loop detected
budget             | tokens / tool calls / time exhausted
success_predicate  | the machine-checkable goal was met  (the healthy exit)
escalation_trigger | handed off to a human (red line, conflict, or 3 failed cycles)
```

Any stop you cannot classify maps to `escalation_trigger` with `exit_detail` — never
invent a seventh value, or the dashboard's vocabulary drifts from the canon.

## 3. Stdlib emit helper

No OTel dependency required to *produce* the record; attach it to whatever exporter you
use (or log it as one JSON line and ship via your logging pipeline).

```python
import json, time

CANON_EXITS = {"max_iterations", "no_progress", "oscillation",
               "budget", "success_predicate", "escalation_trigger"}

def loop_telemetry(run_id, agent, *, iterations, max_iterations,
                   delegation_depth, oscillation_count,
                   budget_consumed, budget_limit,
                   exit_condition, exit_detail, started_at):
    if exit_condition not in CANON_EXITS:
        # never emit an off-canon value; classify unknowns as escalation
        exit_detail = "unmapped:%s -> escalation_trigger; %s" % (exit_condition, exit_detail)
        exit_condition = "escalation_trigger"
    return {
        "agent.run_id": run_id, "agent.name": agent,
        "agent.iterations": iterations, "agent.max_iterations": max_iterations,
        "agent.iteration_pct": round(iterations / max_iterations, 3) if max_iterations else None,
        "agent.delegation_depth": delegation_depth,
        "agent.oscillation_count": oscillation_count,
        "agent.budget_consumed": budget_consumed, "agent.budget_limit": budget_limit,
        "agent.exit_condition": exit_condition, "agent.exit_detail": exit_detail,
        "agent.duration_s": round(time.time() - started_at, 3),
    }

# record = loop_telemetry(...); print(json.dumps(record))  # -> log line / span attributes
```

## 4. Feeding react_trace_analyzer.py

If you also log per-step Thought/Action/Observation records in the canonical trace
schema, `react_trace_analyzer.py` (detections D1-D7) can run over real production traces,
not just test fixtures. The loop-telemetry record above is the *summary*; the per-step
trace is the *detail*. Emit both: the summary powers dashboards, the trace powers
post-hoc runaway analysis.

## 5. Dashboard starter set

- **Stop-reason distribution:** count of runs by `agent.exit_condition` (watch for
  non-`success_predicate` growth).
- **Iteration headroom:** histogram of `agent.iteration_pct` (clustering near 1.0 means
  caps are too tight or the task is too hard).
- **Delegation depth p95:** catches runaway sub-agent trees.
- **Budget burn:** `budget_consumed / budget_limit` p95 by agent.
- **Oscillation incidents:** runs with `oscillation_count > 0`, alerting if sustained.
