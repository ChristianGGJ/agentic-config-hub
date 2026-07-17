# plan-critique

Hostile pre-execution review of a preliminary plan - the mirror of post-hoc
self-evaluation. One capability, two merged check families:

- **Structural critique (PC1-PC8):** missing lifecycle phases (testing/QA,
  legal-compliance, deployment/rollout, training/handoff), estimates without
  a basis, single-point-of-failure owners, missing milestones, duration
  outliers vs sibling tasks.
- **Assumption-register lints (AS1-AS5):** premises without evidence
  sources, invalidation tests, owners, or fresh review dates; a missing or
  empty register is itself CRITICAL.

Every finding carries a severity (CRITICAL / HIGH / MEDIUM / LOW) and a
concrete failure scenario. Verdicts (BLOCK / CONCERNS / CLEAN) feed the
Phase-3 HUMAN GATE.

## Quick start

```bash
# Seeded defects: expect 13 findings, verdict BLOCK, exit 1
python scripts/plan_audit.py assets/sample-plan.json \
    --assumptions assets/sample-assumptions.json --as-of 2026-07-16

# Clean pair: zero findings, score 100, exit 0
python scripts/plan_audit.py assets/clean-plan.json \
    --assumptions assets/clean-assumptions.json --as-of 2026-07-16
```

The expected output for the seeded pair is documented finding-by-finding in
`assets/expected-findings.md`.

## Package contents

- `SKILL.md` - the full rubric: check catalog, three review personas,
  anti-patterns, routing table, delegation and dual-track notes.
- `scripts/plan_audit.py` - deterministic auditor (Python 3.8+ stdlib only,
  `--help`, `--json`, exit codes 0/1/2, no network, no LLM).
- `references/` - persona knowledge bases: planning fallacy and
  reference-class forecasting, the forgotten-step checklist, the assumption
  register method.
- `assets/` - seeded and clean sample plans/registers, the register
  template, and the expected-findings sheet.

Self-contained by hub rule: copy this folder anywhere and it works. Loop
mechanics are deliberately NOT here - they are delegated to the
`agentic-system-architect` references and the `adversarial-reviewer` pattern
donor, cited by name in SKILL.md.
