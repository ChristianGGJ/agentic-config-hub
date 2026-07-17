# plan-baseline-tracking

Deterministic schedule-variance tracking for approved project plans: diff an
immutable baseline `plan.json` against an append-only `status.jsonl` ledger and
get per-task start/finish variance in working days, percent-complete vs
expected, a DCMA-style health-check subset (missed-task percentage, future
actual dates, invalid status transitions, stale updates), and an overall
schedule health verdict.

## Quick start

```bash
# Healthy sample (exits 0)
python scripts/baseline_variance.py --plan assets/sample_plan.json \
    --status assets/sample_status_healthy.jsonl --as-of 2026-07-15

# Slipped sample with seeded defects (exits 1; expected output in assets/)
python scripts/baseline_variance.py --plan assets/sample_plan.json \
    --status assets/sample_status_slipped.jsonl --as-of 2026-07-15

# Machine-readable
python scripts/baseline_variance.py --plan assets/sample_plan.json \
    --status assets/sample_status_healthy.jsonl --as-of 2026-07-15 --json
```

Exit codes: `0` healthy, `1` findings (the CI / escalation trigger), `2` input
error. Python 3.8+ standard library only -- no network, no LLM calls; same
inputs plus the same `--as-of` produce the same report every run.

## Package layout

| Path | Contents |
|------|----------|
| `SKILL.md` | Full skill documentation: interface contract, health checks, mined anti-patterns, routing table |
| `scripts/baseline_variance.py` | The variance and health-check CLI |
| `references/schedule_variance_methods.md` | Method knowledge: variance math, DCMA subset mapping, threshold rationale |
| `references/status_ledger_contract.md` | The plan/status/calendar file contracts (duplicated per the hub portability rule) |
| `assets/` | Sample baseline, healthy and slipped ledgers, sample calendar, expected report |

## Boundaries

This skill only **diffs**. Plan-state persistence across sessions belongs to
the `hybrid-rag-memory` skill; date/CPM math to `critical-path-scheduler`;
replan decisions to `slip-driven-replanning`; PM-tool exports to
`plan-ticket-export`. Cost/dollar EVM is out of scope in v1 by design.
