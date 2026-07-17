# Expected Findings for the Seeded Sample

The pair `sample-plan.json` + `sample-assumptions.json` ships with deliberately
seeded defects so you can verify `plan_audit.py` end to end. Run it with the
pinned as-of date (staleness checks depend on it - pinning keeps the run
reproducible):

```bash
python scripts/plan_audit.py assets/sample-plan.json \
    --assumptions assets/sample-assumptions.json \
    --as-of 2026-07-16 --stale-days 90
```

Expected: **13 findings**, severity counts `CRITICAL=1 HIGH=6 MEDIUM=5 LOW=1`,
score `0/100`, verdict `BLOCK`, gate `FAIL` (default `--fail-on high`),
**exit code 1**.

## Finding-by-finding

| # | Check | Severity | Location | Seeded defect |
|---|-------|----------|----------|---------------|
| 1 | PC1 | CRITICAL | plan-level | No task anywhere matches testing/QA vocabulary - the plan ships unverified |
| 2 | AS1 | HIGH | assumption:ASM-1 | `evidence_source` missing: the sandbox-availability premise has no traceable origin |
| 3 | AS2 | HIGH | assumption:ASM-2 | `invalidation_test` missing: nothing would reveal the component-library premise is false |
| 4 | PC2 | HIGH | plan-level | No legal/compliance review task, despite payment flows in scope |
| 5 | PC5 | HIGH | task:T2 | `duration_days: 6` with no `estimate_basis` |
| 6 | PC5 | HIGH | task:T7 | `duration_days: 16` with no `estimate_basis` |
| 7 | PC6 | HIGH | owner:alice | alice owns 6 of 8 owned tasks (75% - at the HIGH concentration threshold) |
| 8 | AS3 | MEDIUM | assumption:ASM-3 | `owner` missing: nobody is accountable for re-testing the data-volume premise |
| 9 | AS4 | MEDIUM | assumption:ASM-4 | `last_reviewed: 2025-11-02` is 256 days before the as-of date (2x the 90-day threshold) |
| 10 | PC4 | MEDIUM | plan-level | No training/handoff task for the operating team |
| 11 | PC7 | MEDIUM | plan-level | No task carries `milestone: true` - zero slip-detection points |
| 12 | PC8 | MEDIUM | task:T4 | 45 days vs sibling median 6 days in wbs group `2` (ratio 7.50 - severe outlier) |
| 13 | PC8 | LOW | task:T7 | 16 days vs sibling median 6 days in wbs group `2` (ratio 2.67 - mild outlier) |

## What deliberately PASSES

- **PC3 (deployment/rollout)** - task T8 "Production deployment and rollout"
  covers it. The sample proves checks pass when the phase is present.
- **AS5 (register presence)** - the register exists and is non-empty. Run the
  plan WITHOUT `--assumptions` to see AS5 fire as CRITICAL.
- **ASM-5** - a fully populated, recently reviewed assumption. Zero findings.

## Semantic defects the script canNOT see (persona territory)

- T4's `estimate_basis` is "Team judgment" - present, so PC5 passes, but it is
  an inside-view basis the Pessimist-PM persona must reject (no reference
  class).
- ASM-4's `evidence_source` is "Informal note from finance, 2025" - present,
  so AS1 passes, but it is weak evidence for a regulatory premise; the
  Assumption Hunter should demand written counsel confirmation.

This is the honesty split in action: the script checks presence and structure,
the personas check meaning, the human gate decides.

## Clean pair

`clean-plan.json` + `clean-assumptions.json` pass every check:

```bash
python scripts/plan_audit.py assets/clean-plan.json \
    --assumptions assets/clean-assumptions.json --as-of 2026-07-16
```

Expected: zero findings, score `100/100`, verdict `CLEAN`, **exit code 0**.
