# wbs-decomposition

Decompose a macro objective into a work breakdown structure of manageable,
estimable, deliverable-oriented subtasks - then prove the structure is sound
before any human wastes review time on a malformed hierarchy.

One capability, one transformation: objective + constraints in, validated WBS
out, with leaf tasks serialized to the hub canonical `plan.json` contract
(`id`, `description`, `depends_on: []` stubs plus tolerated extras like
`wbs_id`, `deliverable`, `owner`, `estimate_hours`).

## Quick start

```bash
# Validate the shipped sample (depth bounds default to 2-4 levels)
python scripts/wbs_validator.py assets/sample_wbs.json

# Enforce the 8/80 estimate rule and get machine-readable output
python scripts/wbs_validator.py assets/sample_wbs.json --check-estimates --json

# Emit leaf tasks in the shared plan.json contract (only on PASS)
python scripts/wbs_validator.py assets/sample_wbs.json --emit-tasks plan.json
```

Exit codes: `0` PASS, `1` structural gate fail, `2` usage/input error.

## Contents

- `SKILL.md` - methodology, validator checks, anti-patterns, routing table
- `scripts/wbs_validator.py` - stdlib-only structural validator + emitter
- `references/wbs_decomposition_methodology.md` - decomposition knowledge base
- `references/plan_json_contract.md` - duplicated hub plan.json contract
- `assets/sample_wbs.json` - passing nested-hierarchy sample
- `assets/sample_wbs_failing.json` - flat-format sample with seeded defects
- `assets/expected_plan.json` - exact `--emit-tasks` output for the sample
- `assets/wbs-authoring-template.md` - starting skeleton for new WBS files

Honest limits: the validator checks structure only. Semantic completeness
(the real 100-percent rule) belongs to plan-critique and the human gate.

Python 3.8+, standard library only, no network, no LLM calls. Copy this
folder anywhere and it works.
